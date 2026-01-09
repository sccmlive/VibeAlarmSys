DOMAIN = "vibe_alarm_sys"

CONF_ALARM_ENTITY = "alarm_entity"
# Legacy single-target keys (kept for backward compatibility)
CONF_ESPHOME_DEVICE = "esphome_device_id"
CONF_NODE_NAME = "node_name"

# New multi-target keys
CONF_ESPHOME_DEVICES = "esphome_device_ids"
CONF_NODE_NAMES = "node_names"

CONF_SEND_PANEL_NAME = "send_panel_name"
CONF_SEND_SOURCE_TEXT = "send_source_text"

DEFAULT_SEND_PANEL_NAME = True
DEFAULT_SEND_SOURCE_TEXT = True

# --- Hybrid Trigger Detection (stable + universal) ---
# The integration can track recently triggered sensors and, when the alarm panel switches
# to "triggered", send the most likely sensor name to ESPHome.

# Lookback window (seconds) used to pick the most recent trigger before the alarm.
CONF_ALARM_TRIGGER_LOOKBACK_SECONDS = "alarm_trigger_lookback_seconds"
DEFAULT_ALARM_TRIGGER_LOOKBACK_SECONDS = 10

# If enabled, automatically track binary_sensors with relevant device_class (motion/opening/door/window/garage_door/lock/occupancy/presence)
# so users don't need to manually select every sensor.
CONF_AUTO_TRACK_DEVICE_CLASSES = "auto_track_device_classes"
DEFAULT_AUTO_TRACK_DEVICE_CLASSES = True

# Backward compatible constant name used by older versions.
TRIGGER_WINDOW_SECONDS = DEFAULT_ALARM_TRIGGER_LOOKBACK_SECONDS


# Optional: additional entities that should trigger a push to ESPHome even if the alarm panel
# itself does not switch to "triggered" (e.g., camera motion binary_sensors).
CONF_TRIGGER_ENTITIES = "trigger_entities"
CONF_TRIGGER_RESET_SECONDS = "trigger_reset_seconds"
CONF_TRIGGER_COOLDOWN_SECONDS = "trigger_cooldown_seconds"

DEFAULT_TRIGGER_RESET_SECONDS = 10
DEFAULT_TRIGGER_COOLDOWN_SECONDS = 5

# If enabled, when a configured trigger entity fires, its friendly name is preferred
# over the alarm panel's zone/source text.
CONF_PREFER_TRIGGER_FRIENDLY_NAME = "prefer_trigger_friendly_name"
DEFAULT_PREFER_TRIGGER_FRIENDLY_NAME = True
