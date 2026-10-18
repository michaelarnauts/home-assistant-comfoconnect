"""Constants for the ComfoConnect integration."""

DOMAIN = "comfoconnect"

CONF_LOCAL_UUID = "local_uuid"
CONF_UUID = "uuid"

SERVICE_START_BOOST = "start_boost"
ATTR_DURATION = "duration"

# PDO 337 is the bit set of running preset schedule timers (bit 6 boost, bit 11 away). The library only knows it as "sensor_337".
SENSOR_PRESET_TIMERS = 337
