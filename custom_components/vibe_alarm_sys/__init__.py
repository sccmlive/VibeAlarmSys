from __future__ import annotations

from collections import deque
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALARM_ENTITY,
    CONF_ESPHOME_DEVICE,
    CONF_NODE_NAME,
    CONF_SEND_PANEL_NAME,
    CONF_SEND_SOURCE_TEXT,
    DOMAIN,
    TRIGGER_WINDOW_SECONDS,
)

PLATFORMS: list[str] = []


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    """Return a readable name for an entity."""
    st = hass.states.get(entity_id)
    if not st:
        return entity_id

    # Preferred: HA State.name (already resolves friendly name)
    name = getattr(st, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()

    fn = (st.attributes or {}).get("friendly_name")
    if isinstance(fn, str) and fn.strip():
        return fn.strip()

    return entity_id


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    alarm_entity = entry.data[CONF_ALARM_ENTITY]
    node = entry.data[CONF_NODE_NAME]  # must match ESPHome service prefix in HA (underscored)

    send_panel_name = entry.data.get(CONF_SEND_PANEL_NAME, True)
    send_source_text = entry.data.get(CONF_SEND_SOURCE_TEXT, True)

    # ESPHome actions appear as services under "esphome"
    svc_set_state = f"{node}_set_alarm_state"
    svc_set_source = f"{node}_set_alarm_source"
    svc_set_panel = f"{node}_set_alarm_panel_name"

    # Panel name (optional): take ESPHome device name, else alarm entity friendly name
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(entry.data[CONF_ESPHOME_DEVICE])
    panel_name = device.name if device and device.name else _friendly_name(hass, alarm_entity)

    # Ring buffer: recently triggered binary_sensors (entity_id, timestamp)
    recent_triggers: deque[tuple[str, dt_util.dt.datetime]] = deque(maxlen=120)

    def _record_trigger(entity_id: str) -> None:
        recent_triggers.append((entity_id, dt_util.utcnow()))

    def _pick_recent_trigger_name() -> str | None:
        """Return friendly name of the most recent trigger within the time window."""
        if not recent_triggers:
            return None
        now = dt_util.utcnow()
        window = timedelta(seconds=TRIGGER_WINDOW_SECONDS)

        # check newest -> oldest
        for entity_id, ts in reversed(recent_triggers):
            if now - ts > window:
                continue
            return _friendly_name(hass, entity_id)
        return None

    async def _safe_call(service: str, data: dict) -> None:
        """Call ESPHome action only if the service exists (device online + action present)."""
        if not hass.services.has_service("esphome", service):
            return
        await hass.services.async_call("esphome", service, data, blocking=False)

    async def _push_state(state_str: str) -> None:
        # 1) Always send alarm state
        await _safe_call(svc_set_state, {"alarm_state": state_str})

        # 2) Optional: panel name
        if send_panel_name:
            await _safe_call(svc_set_panel, {"panel_name": panel_name})

        # 3) Optional: source text
        if not send_source_text:
            return

        if state_str == "triggered":
            source = _pick_recent_trigger_name() or "Unbekannter Auslöser"
            await _safe_call(svc_set_source, {"alarm_source": source})
        else:
            # Clear source on non-trigger states (ESP ignores '-' in your display logic)
            await _safe_call(svc_set_source, {"alarm_source": "-"})

    # --- Listener 1: Alarm panel state changes (per entry!) ---
    @callback
    def _handle_alarm_event(event) -> None:
        new_state = event.data.get("new_state")
        if not new_state:
            return

        st = new_state.state
        if st in (None, "unknown", "unavailable"):
            return

        hass.async_create_task(_push_state(st))

    unsub_alarm = async_track_state_change_event(hass, [alarm_entity], _handle_alarm_event)
    entry.async_on_unload(unsub_alarm)

    # --- Listener 2: Track recently triggered binary_sensors (universal) ---
    @callback
    def _handle_any_state_change(event) -> None:
        entity_id = event.data.get("entity_id")
        if not entity_id or not entity_id.startswith("binary_sensor."):
            return

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state:
            return

        # Only count a real trigger: off -> on
        if old_state.state == "off" and new_state.state == "on":
            _record_trigger(entity_id)

    unsub_bus = hass.bus.async_listen("state_changed", _handle_any_state_change)
    entry.async_on_unload(unsub_bus)

    # On startup: push current state once
    cur = hass.states.get(alarm_entity)
    if cur and cur.state not in (None, "unknown", "unavailable"):
        hass.async_create_task(_push_state(cur.state))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
