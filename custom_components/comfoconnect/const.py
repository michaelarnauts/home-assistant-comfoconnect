"""Constants for the ComfoConnect integration."""

from aiocomfoconnect.const import ProductId

DOMAIN = "comfoconnect"

CONF_LOCAL_UUID = "local_uuid"
CONF_UUID = "uuid"
CONF_AIRFLOW_UNIT = "airflow_unit"

# aiocomfoconnect decodes PDO 224 (Device Airflow Unit) to these identifiers.
AIRFLOW_UNIT_KGPH = "kgph"
AIRFLOW_UNIT_LPS = "lps"
AIRFLOW_UNIT_M3PH = "m3ph"
AIRFLOW_UNITS = (AIRFLOW_UNIT_KGPH, AIRFLOW_UNIT_LPS, AIRFLOW_UNIT_M3PH)
VOLUME_AIRFLOW_UNITS = (AIRFLOW_UNIT_LPS, AIRFLOW_UNIT_M3PH)

SERVICE_START_BOOST = "start_boost"
ATTR_DURATION = "duration"

# The model of a node that doesn't tell its model itself, by product id, as the official app names it. The app calls
# product 5 "ComfoConnect Gateway", but that is the ComfoConnect LAN C, and writes "ComfoConnect PRO" in capitals.
PRODUCT_MODELS = {
    ProductId.COMFOAIRQ: "ComfoAir Q",
    ProductId.COMFOSENSE: "ComfoSense C",
    ProductId.COMFOSWITCH: "ComfoSwitch C",
    ProductId.OPTIONBOX: "Option Box",
    ProductId.ZEHNDERGATEWAY: "ComfoConnect LAN C",
    ProductId.COMFOCOOL: "ComfoCool Q600",
    ProductId.KNXGATEWAY: "ComfoConnect KNX C",
    ProductId.COMFOAIRFLEX: "ComfoAir Flex",
    ProductId.COMFOAIRFLEXCONNECTIONBOARD: "ComfoAir WiFi Connection Module",
    ProductId.CO2SENSOR: "CO2 Sensor C",
    ProductId.COMFOVARNGMAINNODE: "ComfoVar NG Main Node",
    ProductId.COMFOVARNGPERIPHERALNODE: "ComfoVar NG Peripheral Node",
    ProductId.COMFOCLIME: "ComfoClime",
    ProductId.COMFODRY: "ComfoDry",
    ProductId.COMFOPOST: "ComfoPost",
    ProductId.COMFOCONNECTPRO: "ComfoConnect Pro",
}
