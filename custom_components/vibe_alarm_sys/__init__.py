from __future__ import annotations

from collections import deque
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import DOMAIN

RELEVANT_DEVICE_CLASSES = {
    "door",
    "window",
    "opening",
    "garage_door",
    "motion",
    "occupancy",
    "presence",
    "lock",
}

ACTIVE_STATES = {"on", "open", "opened", "true"}


def _normalize_boolish(state: str) -> str:
    # Some integrations may emit True/False, keep it consistent
    if state is True:
        return "true"
    if state is False:
        return "false"
    return str(state).lower()


def _pick_esphome_service(hass: HomeAssistant, base: str) -> str | None:
    """
    Find a working esphome service name in hass.services.
    Tries a couple common patterns.
    """
    candidates = [
        base,
        base.replace("-", "_"),
        base.replace("_", "-"),
    ]
    for svc in candidates:
        if hass.services.has_service("esphome", svc):
            return svc
    return None


async def _safe_esphome_call(
    hass: HomeAssistant,
    service: str,
    data: dict,
) -> None:
    if not hass.services.has_service("esphome", service):
        return
    await hass.services.async_call("esphome", service, data, blocking=False)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    alarm_entity: str = entry.data["alarm_entity"]
    esphome_devices: list[str] = list(entry.data.get("esphome_devices") or [])

    # Default to 60 seconds if missing/empty
    lookback_seconds = int(entry.data.get("alarm_trigger_lookback_seconds") or 60)
    lookback_delta = timedelta(seconds=lookback_seconds)

    # Cache of recent triggers: newest appended at end
    trigger_cache: deque[dict] = deque(maxlen=300)

    # --- Resolve ESPHome service names once (lazy-ish; we also re-check later) ---
    # Expected services (example):
    #  - esphome.<device>_set_alarm_state
    #  - esphome.<device>_set_alarm_source
    #  - esphome.<device>_set_alarm_panel_name
    #
    # Here, "<device>" is the ESPHome entity_id without the "esphome." prefix,
    # e.g. "esphome.vibealarm_wohnzimmer" -> "vibealarm_wohnzimmer"
    def device_slug(esphome_entity_id: str) -> str:
        return esphome_entity_id.split(".", 1)[-1].strip()

    def svc_state(slug: str) -> str:
        return f"{slug}_set_alarm_state"

    def svc_source(slug: str) -> str:
        return f"{slug}_set_alarm_source"

    def svc_panel(slug: str) -> str:
        return f"{slug}_set_alarm_panel_name"

    async def push_to_all(state_text: str | None = None, source_text: str | None = None) -> None:
        # Push to all selected ESPHome devices
        for dev in esphome_devices:
            slug = device_slug(dev)
            if not slug:
                continue

            if state_text is not None:
                service = _pick_esphome_service(hass, svc_state(slug))
                if service:
                    await _safe_esphome_call(hass, service, {"state": state_text})

            if source_text is not None:
                service = _pick_esphome_service(hass, svc_source(slug))
                if service:
                    await _safe_esphome_call(hass, service, {"source": source_text})

            # Optional: also push panel name if your ESPHome supports it
            # We'll use the alarm entity's friendly name if available.
            panel_name = None
            st = hass.states.get(alarm_entity)
            if st:
                panel_name = st.attributes.get("friendly_name") or st.name
            if panel_name:
                service = _pick_esphome_service(hass, svc_panel(slug))
                if service:
                    await _safe_esphome_call(hass, service, {"name": panel_name})

    # --- Binary sensor trigger tracking (universal) ---
    @callback
    def on_binary_sensor_change(event):
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not entity_id or not new_state:
            return

        new_s = _normalize_boolish(new_state.state)
        if new_s in ("unknown", "unavailable", "none"):
            return

        attrs = new_state.attributes or {}
        device_class = attrs.get("device_class")

        if device_class not in RELEVANT_DEVICE_CLASSES:
            return

        old_s = _normalize_boolish(old_state.state) if old_state else None
        if old_s == new_s:
            return

        # Trigger when sensor goes into an "active" state
        if new_s not in ACTIVE_STATES:
            return

        trigger_cache.append(
            {
                "ts": dt_util.utcnow(),
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or entity_id,
                "device_class": device_class,
                "state": new_s,
            }
        )

    async_track_state_change_event(hass, "binary_sensor", on_binary_sensor_change)

    # --- Alarm state tracking ---
    @callback
    def on_alarm_change(event):
        new_state = event.data.get("new_state")
        if not new_state:
            return

        alarm_state = _normalize_boolish(new_state.state)

        async def _handle():
            # Always push state updates
            await push_to_all(state_text=alarm_state)

            # When triggered, try to infer sensor source in lookback window
            if alarm_state == "triggered":
                now = dt_util.utcnow()
                chosen = None
                for item in reversed(trigger_cache):
                    if now - item["ts"] <= lookback_delta:
                        chosen = item
                        break

                # Prefer inferred sensor name; fallback to alarm panel source; final fallback "Alarm"
                source_text = None
                if chosen:
                    source_text = chosen["name"]
                else:
                    source_text = new_state.attributes.get("source") or "Alarm"

                await push_to_all(source_text=source_text)

        hass.async_create_task(_handle())

    async_track_state_change_event(hass, alarm_entity, on_alarm_change)

    # Push initial state once after setup (helps after restart)
    st0 = hass.states.get(alarm_entity)
    if st0:
        hass.async_create_task(push_to_all(state_text=_normalize_boolish(st0.state)))

    return True
