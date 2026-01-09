from __future__ import annotations

from collections import deque
from datetime import timedelta
import re
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALARM_ENTITY,
    CONF_ESPHOME_DEVICE,
    CONF_ESPHOME_DEVICES,
    CONF_NODE_NAME,
    CONF_SEND_PANEL_NAME,
    CONF_SEND_SOURCE_TEXT,
    CONF_TRIGGER_ENTITIES,
    DOMAIN,
    TRIGGER_WINDOW_SECONDS,
)

ACTIVE_STATES = {"on", "open", "opened", "true", "detected"}

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

    # --- Multi ESPHome targets ---
    device_ids = entry.data.get(CONF_ESPHOME_DEVICES) or []
    if not device_ids and entry.data.get(CONF_ESPHOME_DEVICE):
        device_ids = [entry.data[CONF_ESPHOME_DEVICE]]

    def _slugify(val: str) -> str:
        v = val.lower()
        v = re.sub(r"[^a-z0-9_]+", "_", v)
        v = re.sub(r"_+", "_", v).strip("_")
        return v

    def _node_from_device_id(dev_id: str) -> str | None:
        dev_reg = dr.async_get(hass)
        dev = dev_reg.async_get(dev_id)
        if not dev:
            return None
        # Preferred: identifier ("esphome", "<node_name>")
        for domain, ident in dev.identifiers:
            if domain == "esphome" and isinstance(ident, str) and ident.strip():
                return _slugify(ident)
        # Fallback: stored node_name (legacy)
        stored = entry.data.get(CONF_NODE_NAME)
        if isinstance(stored, str) and stored.strip():
            return _slugify(stored)
        # Last fallback: device name
        if dev.name:
            return _slugify(dev.name)
        return None

    # Build list of (node_prefix, panel_name)
    dev_reg = dr.async_get(hass)
    alarm_panel_name = _friendly_name(hass, alarm_entity)
    targets: list[tuple[str, str]] = []
    for dev_id in device_ids:
        node_prefix = _node_from_device_id(dev_id)
        if not node_prefix:
            continue
        dev = dev_reg.async_get(dev_id)
        pn = dev.name if dev and dev.name else alarm_panel_name
        targets.append((node_prefix, pn))
    manual_triggers = set(entry.data.get(CONF_TRIGGER_ENTITIES, []) or [])
    recent_triggers: deque[tuple[str, dt_util.dt.datetime]] = deque(maxlen=120)

    # Cooldown to avoid spamming ESPHome when a manual trigger chatters.
    manual_last_sent: dict[str, dt_util.dt.datetime] = {}
    MANUAL_COOLDOWN_SECONDS = 3
    MANUAL_RESET_SECONDS = 10

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

    def _fallback_scan_last_changed() -> str | None:
        """Fallback: scan current HA states to find a likely trigger.

        Used when the alarm panel flips to triggered before we recorded the sensor.
        We prefer entities that are currently active and changed recently.
        """
        now = dt_util.utcnow()
        window = timedelta(seconds=TRIGGER_WINDOW_SECONDS)

        best_name: str | None = None
        best_ts = None

        for st in hass.states.async_all("binary_sensor"):
            if not st:
                continue

            entity_id = st.entity_id
            attrs = st.attributes or {}
            dc = attrs.get("device_class")

            # Accept either alarm-like device_classes or explicitly configured manual triggers.
            if dc is None and entity_id not in manual_triggers:
                continue
            if dc is not None and dc not in {"door", "window", "opening", "garage_door", "motion", "occupancy", "presence", "lock"} and entity_id not in manual_triggers:
                continue

            state = (st.state or "").lower()
            if state not in ACTIVE_STATES:
                continue

            ts = getattr(st, "last_changed", None)
            if not ts or now - ts > window:
                continue

            if best_ts is None or ts > best_ts:
                best_ts = ts
                best_name = attrs.get("friendly_name") or entity_id

        return best_name

    async def _safe_call(service: str, data: dict) -> None:
        """Call ESPHome action only if the service exists (device online + action present)."""
        if not hass.services.has_service("esphome", service):
            return
        await hass.services.async_call("esphome", service, data, blocking=False)

    async def _push_state(state_str: str) -> None:
        # 1) Always send alarm state
        for node_prefix, _pn in targets:
            await _safe_call(f"{node_prefix}_set_alarm_state", {"alarm_state": state_str})

        # 2) Optional: panel name
        if send_panel_name:
            for node_prefix, _pn in targets:
                await _safe_call(f"{node_prefix}_set_alarm_panel_name", {"panel_name": _pn})

        # 3) Optional: source text
        if not send_source_text:
            return

        if state_str == "triggered":
            # Small delay to avoid race conditions where the alarm state changes
            # slightly before the triggering sensor state change is processed.
            # Wait a short moment so the triggering sensor's state change can be
            # processed before we pick the last trigger (fixes race conditions).
            await asyncio.sleep(1.5)
            source = _pick_recent_trigger_name() or _fallback_scan_last_changed() or "Alarm"
            for node_prefix, _pn in targets:
                await _safe_call(f"{node_prefix}_set_alarm_source", {"alarm_source": source})
        else:
            # Clear source on non-trigger states (ESP ignores '-' in your display logic)
            for node_prefix, _pn in targets:
                await _safe_call(f"{node_prefix}_set_alarm_source", {"alarm_source": "-"})

    async def _push_manual_trigger(entity_id: str) -> None:
        """Send an immediate 'triggered' pulse to ESPHome when a manual trigger fires.

        This is used for sensors like Arlo motion where the alarm panel might not
        switch to 'triggered'. After a short delay, the display is restored to the
        current alarm panel state.
        """
        name = _friendly_name(hass, entity_id)

        # Push triggered + source to all targets
        for node_prefix, _pn in targets:
            await _safe_call(f"{node_prefix}_set_alarm_state", {"alarm_state": "triggered"})
        if send_panel_name:
            for node_prefix, _pn in targets:
                await _safe_call(f"{node_prefix}_set_alarm_panel_name", {"panel_name": _pn})
        if send_source_text:
            for node_prefix, _pn in targets:
                await _safe_call(f"{node_prefix}_set_alarm_source", {"alarm_source": name})

        # Restore current alarm panel state after a short pulse
        await asyncio.sleep(MANUAL_RESET_SECONDS)
        cur = hass.states.get(alarm_entity)
        if cur and cur.state not in (None, "unknown", "unavailable"):
            await _push_state(cur.state)

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

        # Count a real trigger for alarm-like sensors
        old = (old_state.state or "").lower()
        new = (new_state.state or "").lower()
        if new in ("unknown", "unavailable", "none"):
            return

        # 1) Always respect manually selected trigger entities (e.g., Arlo motion binary_sensors)
        if entity_id in manual_triggers:
            if old != new and new in ACTIVE_STATES:
                _record_trigger(entity_id)
                # Rate limit to avoid rapid repeats
                now = dt_util.utcnow()
                last = manual_last_sent.get(entity_id)
                if not last or (now - last) > timedelta(seconds=MANUAL_COOLDOWN_SECONDS):
                    manual_last_sent[entity_id] = now
                    hass.async_create_task(_push_manual_trigger(entity_id))
            return

        # 2) Universal tracking for binary_sensors used in alarm setups
        if old != new and new in ACTIVE_STATES:
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
