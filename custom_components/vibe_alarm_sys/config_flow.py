from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import async_get as async_get_dev_reg

from .const import (
    DOMAIN,
    CONF_ALARM_ENTITY,
    CONF_ESPHOME_DEVICE,
    CONF_ESPHOME_DEVICES,
    CONF_NODE_NAME,
    CONF_SEND_PANEL_NAME,
    CONF_SEND_SOURCE_TEXT,
    CONF_TRIGGER_ENTITIES,
    DEFAULT_SEND_PANEL_NAME,
    DEFAULT_SEND_SOURCE_TEXT,
)


def _slugify_node_name(name: str) -> str:
    s = name.strip().lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


async def _guess_esphome_node_name_from_device(hass, device_id: str) -> str | None:
    dev_reg = async_get_dev_reg(hass)
    device = dev_reg.async_get(device_id)
    if not device:
        return None
    if device.name:
        return _slugify_node_name(device.name)
    return None


class VibrationsalarmBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            alarm_entity = user_input[CONF_ALARM_ENTITY]
            esphome_device_ids = user_input.get(CONF_ESPHOME_DEVICES) or []
            if not esphome_device_ids and CONF_ESPHOME_DEVICE in user_input:
                esphome_device_ids = [user_input[CONF_ESPHOME_DEVICE]]
            send_panel_name = user_input.get(CONF_SEND_PANEL_NAME, DEFAULT_SEND_PANEL_NAME)
            send_source_text = user_input.get(CONF_SEND_SOURCE_TEXT, DEFAULT_SEND_SOURCE_TEXT)
            trigger_entities = user_input.get(CONF_TRIGGER_ENTITIES, []) or []

            node_name = user_input.get(CONF_NODE_NAME, "").strip()
            if not node_name:
                guessed = await _guess_esphome_node_name_from_device(self.hass, esphome_device_ids[0])
                if guessed:
                    node_name = guessed
                else:
                    errors[CONF_NODE_NAME] = "node_required"

            if not errors:
                title = f"VibeAlarmSys Bridge ({alarm_entity} → {node_name})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ALARM_ENTITY: alarm_entity,
                        CONF_ESPHOME_DEVICES: esphome_device_ids,
                        CONF_ESPHOME_DEVICE: esphome_device_ids[0],
                        CONF_NODE_NAME: node_name,
                        CONF_SEND_PANEL_NAME: send_panel_name,
                        CONF_SEND_SOURCE_TEXT: send_source_text,
                        CONF_TRIGGER_ENTITIES: trigger_entities,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ALARM_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="alarm_control_panel")
                ),
                vol.Required(CONF_ESPHOME_DEVICES): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="esphome", multiple=True)
                ),
                vol.Optional(CONF_NODE_NAME, default=""): str,
                vol.Optional(CONF_SEND_PANEL_NAME, default=DEFAULT_SEND_PANEL_NAME): bool,
                vol.Optional(CONF_SEND_SOURCE_TEXT, default=DEFAULT_SEND_SOURCE_TEXT): bool,
                vol.Optional(CONF_TRIGGER_ENTITIES, default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
