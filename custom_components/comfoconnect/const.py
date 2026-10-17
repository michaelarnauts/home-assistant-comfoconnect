"""Constants for the ComfoConnect integration."""

DOMAIN = "comfoconnect"

CONF_LOCAL_UUID = "local_uuid"
CONF_UUID = "uuid"

SERVICE_START_BOOST = "start_boost"
ATTR_DURATION = "duration"

# Postheater (option box) PDO ids. aiocomfoconnect already decodes these as generic "sensor_<id>" entries.
# The after-postheater temperature is PDO 221, which is already exposed as the supply temperature.
SENSOR_POSTHEATER_TEMP_BEFORE = 278
SENSOR_POSTHEATER_STATE = 401
SENSOR_POSTHEATER_PRESENT = 402
