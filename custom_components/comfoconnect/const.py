"""Constants for the ComfoConnect integration."""

from aiocomfoconnect.const import ProductId

DOMAIN = "comfoconnect"

CONF_LOCAL_UUID = "local_uuid"
CONF_UUID = "uuid"

SERVICE_START_BOOST = "start_boost"
ATTR_DURATION = "duration"

# The model of a node that doesn't tell its model itself, by product id, as the official app names it.
PRODUCT_MODELS = {
    ProductId.CO2SENSOR: "CO2 Sensor C",
}
