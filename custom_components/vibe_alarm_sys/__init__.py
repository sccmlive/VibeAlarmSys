from __future__ import annotations

import asyncio

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
    CONF_ESPHOME_DEVICES,
    CONF_NODE_NAMES,
    CONF_SEND_PANEL_NAME,
    CONF_SEND_SOURCE_TEXT,
    DOMAIN,
    TRIGGER_WINDOW_SECONDS,
    CONF_ALARM_TRIGGER_LOOKBACK_SECONDS,
    DEFAULT_ALARM_TRIGGER_LOOKBACK_SECONDS,
    CONF_AUTO_TRACK_DEVICE_CLASSES,
    DEFAULT_AUTO_TRACK_DEVICE_CLASSES,
    CONF_TRIGGER_ENTITIES,
    CONF_TRIGGER_RESET_SECONDS,
    CONF_TRIGGER_COOLDOWN_SECONDS,
    DEFAULT_TRIGGER_RESET_SECONDS,
    DEFAULT_TRIGGER_COOLDOWN_SECONDS,
    CONF_PREFER_TRIGGER_FRIENDLY_NAME,
    DEFAULT_PREFER_TRIGGER_FRIENDLY_NAME,
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
    send_panel_name = entry.data.get(CONF_SEND_PANEL_NAME, True)
    send_source_text = entry.data.get(CONF_SEND_SOURCE_TEXT, True)
    prefer_trigger_friendly_name = entry.data.get(CONF_PREFER_TRIGGER_FRIENDLY_NAME, DEFAULT_PREFER_TRIGGER_FRIENDLY_NAME)

    trigger_entities: list[str] = entry.data.get(CONF_TRIGGER_ENTITIES, [])
    trigger_reset_seconds: int = int(entry.data.get(CONF_TRIGGER_RESET_SECONDS, DEFAULT_TRIGGER_RESET_SECONDS))
    trigger_cooldown_seconds: int = int(entry.data.get(CONF_TRIGGER_COOLDOWN_SECONDS, DEFAULT_TRIGGER_COOLDOWN_SECONDS))
    lookback_seconds: int = int(entry.data.get(CONF_ALARM_TRIGGER_LOOKBACK_SECONDS, DEFAULT_ALARM_TRIGGER_LOOKBACK_SECONDS))
    auto_track_device_classes: bool = bool(entry.data.get(CONF_AUTO_TRACK_DEVICE_CLASSES, DEFAULT_AUTO_TRACK_DEVICE_CLASSES))

    # --- Resolve targets (multi-device) ---
    # New format: lists in entry.data
    device_ids: list[str] | None = entry.data.get(CONF_ESPHOME_DEVICES)
    node_names: list[str] | None = entry.data.get(CONF_NODE_NAMES)

    # Backward compatibility (old single-target keys)
    if not device_ids:
        legacy_dev = entry.data.get(CONF_ESPHOME_DEVICE)
        if legacy_dev:
            device_ids = [legacy_dev]
    if not node_names:
        legacy_node = entry.data.get(CONF_NODE_NAME)
        if legacy_node:
            node_names = [legacy_node]

    if not device_ids or not node_names:
        # Misconfigured entry; nothing to do
        return False

    targets: list[dict[str, str]] = []
    dev_reg = dr.async_get(hass)
    for idx, node in enumerate(node_names):
        dev_id = device_ids[idx] if idx < len(device_ids) else device_ids[-1]
        device = dev_reg.async_get(dev_id)
        panel_name = device.name if device and device.name else _friendly_name(hass, alarm_entity)
        targets.append(
            {
                "node": node,
                "device_id": dev_id,
                "panel_name": panel_name,
            }
        )

    # Ring buffer: recently triggered sensors (entity_id, friendly_name, timestamp)
    recent_triggers: deque[tuple[str, str, dt_util.dt.datetime]] = deque(maxlen=240)

    # Last known 'source' attribute from the alarm panel (Alarmo zone text etc.)
    last_alarm_source: str | None = None

    def _record_trigger(entity_id: str, name: str | None = None) -> None:
        recent_triggers.append((entity_id, (name or _friendly_name(hass, entity_id)), dt_util.utcnow()))

    def _pick_recent_trigger_name() -> str | None:
        """Return friendly name of the most recent trigger within the lookback window."""
        if not recent_triggers:
            return None
        now = dt_util.utcnow()
        # Prefer configured lookback, fall back to legacy constant.
        window = timedelta(seconds=lookback_seconds or TRIGGER_WINDOW_SECONDS)

        # check newest -> oldest
        for entity_id, name, ts in reversed(recent_triggers):
            if now - ts > window:
                continue
            return name
        return None

    async def _safe_call(service: str, data: dict) -> None:
        """Call ESPHome action only if the service exists (device online + action present)."""
        if not hass.services.has_service("esphome", service):
            return
        await hass.services.async_call("esphome", service, data, blocking=False)

    async def _push_to_all(state_str: str) -> None:
        """Push alarm state (and optional info) to all configured ESPHome targets."""
        for t in targets:
            node = t["node"]
            svc_set_state = f"{node}_set_alarm_state"
            svc_set_source = f"{node}_set_alarm_source"
            svc_set_panel = f"{node}_set_alarm_panel_name"

            # 1) Always send alarm state
            await _safe_call(svc_set_state, {"alarm_state": state_str})

            # 2) Optional: panel name (per device)
            if send_panel_name:
                await _safe_call(svc_set_panel, {"panel_name": t["panel_name"]})

            # 3) Optional: source text
            if not send_source_text:
                continue

            if state_str == "triggered":
                recent = _pick_recent_trigger_name()
                panel_src = last_alarm_source

                if prefer_trigger_friendly_name:
                    # Prefer the most recent trigger entity's friendly name, fall back to panel source
                    source = recent or panel_src or "Alarm"
                else:
                    # Prefer the alarm panel's own source/zone text, fall back to recent trigger name
                    source = panel_src or recent or "Alarm"

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
        nonlocal last_alarm_source
        last_alarm_source = (
            new_state.attributes.get("source")
            or new_state.attributes.get("alarm_source")
            or new_state.attributes.get("changed_by")
        )
        if st in (None, "unknown", "unavailable"):
            return

        hass.async_create_task(_push_to_all(st))

    unsub_alarm = async_track_state_change_event(hass, [alarm_entity], _handle_alarm_event)
    entry.async_on_unload(unsub_alarm)


    # --- Listener 1b: Additional trigger entities (e.g., camera motion binary_sensors) ---
    _last_trigger_ts: dict[str, float] = {}

    async def _handle_trigger(entity_id: str, friendly: str) -> None:
        """Push a short 'triggered' pulse to all ESPHome targets."""
        # Record this trigger so that, if Alarmo also flips to triggered shortly after,
        # we can report the same sensor name.
        _record_trigger(entity_id, friendly)
        # Send source (if enabled) and trigger state
        if send_source_text:
            # Use the triggering entity friendly name
            await _push_to_all("triggered")  # _push_to_all will set source based on recent triggers
            # Override source with the entity name for accuracy (optional)
            if prefer_trigger_friendly_name:
                for t in targets:
                    svc_set_source = f"{t['node']}_set_alarm_source"
                    await _safe_call(svc_set_source, {"alarm_source": friendly})
        else:
            await _push_to_all("triggered")

        async def _reset_later() -> None:
            await asyncio.sleep(trigger_reset_seconds)
            # Restore the current alarm panel state (so we don't fight Alarmo)
            st = hass.states.get(alarm_entity)
            restore = st.state if st else "disarmed"
            await _push_to_all(restore)

        hass.async_create_task(_reset_later())

    @callback
    def _handle_trigger_entities(event) -> None:
        entity_id = event.data.get("entity_id")
        if not entity_id:
            return
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state:
            return

        # Cooldown per entity to avoid spamming
        now_ts = dt_util.utcnow().timestamp()
        last = _last_trigger_ts.get(entity_id, 0.0)
        if now_ts - last < trigger_cooldown_seconds:
            return

        # Only trigger on meaningful transitions
        domain = entity_id.split(".", 1)[0]
        triggered = False
        if domain == "binary_sensor":
            if (old_state is None or old_state.state != "on") and new_state.state == "on":
                triggered = True
        else:
            # For other entity types, any state change away from unknown/unavailable can trigger
            if new_state.state not in ("unknown", "unavailable") and (not old_state or old_state.state != new_state.state):
                triggered = True

        if not triggered:
            return

        _last_trigger_ts[entity_id] = now_ts
        friendly = new_state.attributes.get("friendly_name") or entity_id
        # Record in the shared recent-trigger cache, so an imminent alarm trigger can
        # resolve to this sensor name.
        _record_trigger(entity_id, str(friendly))
        hass.async_create_task(_handle_trigger(entity_id, friendly))

    if trigger_entities:
        unsub_triggers = async_track_state_change_event(hass, trigger_entities, _handle_trigger_entities)
        entry.async_on_unload(unsub_triggers)

    # --- Listener 2: Track recently triggered sensors (hybrid auto-tracking) ---
    _AUTO_DEVICE_CLASSES = {"motion", "opening", "door", "window", "garage_door", "lock", "occupancy", "presence"}

    def _is_meaningful_trigger(old_s: str | None, new_s: str | None) -> bool:
        if not new_s or new_s in ("unknown", "unavailable"):
            return False

        # Treat transitions into "on" or "open" as triggers.
        trigger_states = {"on", "open", "unlocked"}
        if new_s in trigger_states and old_s not in trigger_states:
            return True

        # Common contact representation: closed -> open
        if old_s == "closed" and new_s == "open":
            return True

        return False
    @callback
    def _handle_any_state_change(event) -> None:
        entity_id = event.data.get("entity_id")
        if not auto_track_device_classes:
            return
        if not entity_id or not entity_id.startswith("binary_sensor."):
            return

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not old_state:
            return

        dev_class = (new_state.attributes or {}).get("device_class")
        if dev_class not in _AUTO_DEVICE_CLASSES:
            return

        if _is_meaningful_trigger(old_state.state, new_state.state):
            name = new_state.attributes.get("friendly_name") or getattr(new_state, "name", None) or entity_id
            _record_trigger(entity_id, str(name))

    unsub_bus = hass.bus.async_listen("state_changed", _handle_any_state_change)
    entry.async_on_unload(unsub_bus)

    # On startup: push current state once
    cur = hass.states.get(alarm_entity)
    if cur and cur.state not in (None, "unknown", "unavailable"):
        hass.async_create_task(_push_to_all(cur.state))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to the new multi-target format."""
    if entry.version >= 4:
        return True

    data = dict(entry.data)

    # Convert old single-target fields into list-based fields
    legacy_dev = data.pop(CONF_ESPHOME_DEVICE, None)
    legacy_node = data.pop(CONF_NODE_NAME, None)

    if legacy_dev and CONF_ESPHOME_DEVICES not in data:
        data[CONF_ESPHOME_DEVICES] = [legacy_dev]
    if legacy_node and CONF_NODE_NAMES not in data:
        data[CONF_NODE_NAMES] = [legacy_node]

    data.setdefault(CONF_TRIGGER_ENTITIES, [])
    data.setdefault(CONF_TRIGGER_RESET_SECONDS, DEFAULT_TRIGGER_RESET_SECONDS)
    data.setdefault(CONF_TRIGGER_COOLDOWN_SECONDS, DEFAULT_TRIGGER_COOLDOWN_SECONDS)
    data.setdefault(CONF_PREFER_TRIGGER_FRIENDLY_NAME, DEFAULT_PREFER_TRIGGER_FRIENDLY_NAME)
    data.setdefault(CONF_ALARM_TRIGGER_LOOKBACK_SECONDS, DEFAULT_ALARM_TRIGGER_LOOKBACK_SECONDS)
    data.setdefault(CONF_AUTO_TRACK_DEVICE_CLASSES, DEFAULT_AUTO_TRACK_DEVICE_CLASSES)

    hass.config_entries.async_update_entry(entry, data=data, version=4)
    return True