DOMAIN = "vibe_alarm_sys"

CONF_ALARM_ENTITY = "alarm_entity"
CONF_ESPHOME_DEVICE = "esphome_device_id"
CONF_ESPHOME_DEVICES = "esphome_device_ids"
CONF_ESPHOME_NODES = "esphome_nodes"
CONF_NODE_NAME = "node_name"
CONF_TRIGGER_ENTITIES = "trigger_entities"

CONF_SEND_PANEL_NAME = "send_panel_name"
CONF_SEND_SOURCE_TEXT = "send_source_text"

DEFAULT_SEND_PANEL_NAME = True
DEFAULT_SEND_SOURCE_TEXT = True

# --- Universal Trigger Detection (no Alarmo dependency) ---
# When the alarm_control_panel switches to "triggered", the integration will look for the
# most recently triggered binary_sensor (off -> on) within this time window and send its
# friendly name to the ESPHome device via set_alarm_source.
TRIGGER_WINDOW_SECONDS = 60
