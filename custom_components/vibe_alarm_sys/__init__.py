from __future__ import annotations

from datetime import timedelta
from collections import deque

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    lookback_seconds = int(entry.data.get("alarm_trigger_lookback_seconds") or 60)
    lookback_delta = timedelta(seconds=lookback_seconds)

    trigger_cache: deque[dict] = deque(maxlen=100)

    @callback
    def on_binary_sensor_change(event):
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not entity_id or not new_state:
            return

        attrs = new_state.attributes or {}
        device_class = attrs.get("device_class")

        if device_class not in RELEVANT_DEVICE_CLASSES:
            return

        old = old_state.state if old_state else None
        new = new_state.state

        if old == new:
            return

        # aktive Zustände erkennen (universell)
        if new not in ("on", "open", "opened", "true"):
            return

        trigger_cache.append(
            {
                "ts": dt_util.utcnow(),
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or entity_id,
            }
        )

    async_track_state_change_event(
        hass,
        "binary_sensor",
        on_binary_sensor_change,
    )

    alarm_entity = entry.data["alarm_entity"]

    @callback
    async def on_alarm_change(event):
        new_state = event.data.get("new_state")
        if not new_state or new_state.state != "triggered":
            return

        now = dt_util.utcnow()
        chosen = None

        for item in reversed(trigger_cache):
            if now - item["ts"] <= lookback_delta:
                chosen = item
                break

        source_text = (
            chosen["name"]
            if chosen
            else new_state.attributes.get("source")
            or "Alarm"
        )

        # hier wird später an ESPHome gepusht
        hass.data.setdefault(DOMAIN, {})["last_source"] = source_text

    async_track_state_change_event(
        hass,
        alarm_entity,
        on_alarm_change,
    )

    return True
