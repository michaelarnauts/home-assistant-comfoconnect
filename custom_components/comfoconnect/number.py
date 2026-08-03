"""Number entities for the ComfoConnect integration."""

from __future__ import annotations

from dataclasses import dataclass

from aiocomfoconnect.const import (
    UNIT_TEMPHUMCONTROL,
    UNIT_VENTILATIONCONFIG,
    PdoType,
    VentilationSpeed,
)
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, ComfoConnectBridge

PROPERTY_RANGE = 0x20
PROPERTY_STEP = 0x40


@dataclass
class ComfoConnectNumberRequiredKeysMixin:
    """Mixin for required number keys."""

    unit: int
    subunit: int
    property_id: int
    property_type: int


@dataclass
class ComfoConnectNumberEntityDescription(NumberEntityDescription, ComfoConnectNumberRequiredKeysMixin):
    """Describes a ComfoConnect number entity."""

    scale: int = 1
    speed: str | None = None


NUMBER_TYPES = (
    ComfoConnectNumberEntityDescription(
        key="airflow_away",
        name="Away airflow target",
        icon="mdi:fan-speed-1",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=3,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.AWAY,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_low",
        name="Low airflow target",
        icon="mdi:fan-speed-1",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=4,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.LOW,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_medium",
        name="Medium airflow target",
        icon="mdi:fan-speed-2",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=5,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.MEDIUM,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_high",
        name="High airflow target",
        icon="mdi:fan-speed-3",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=6,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.HIGH,
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_heating",
        name="Heating RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=2,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_cooling",
        name="Cooling RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=3,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_warm",
        name="Warm profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=10,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_normal",
        name="Normal profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=11,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_cool",
        name="Cool profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=12,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect number entities."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    numbers = [ComfoConnectNumber(ccb=ccb, config_entry=config_entry, description=description) for description in NUMBER_TYPES]

    async_add_entities(numbers, True)


class ComfoConnectNumber(NumberEntity):
    """Representation of a ComfoConnect writable numeric property."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = True
    entity_description: ComfoConnectNumberEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoConnectNumberEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect number."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )

    async def async_update(self) -> None:
        """Update the value and device-provided constraints."""
        self._attr_native_value = self._decode_value(
            await self._ccb.get_single_property(
                self.entity_description.unit,
                self.entity_description.subunit,
                self.entity_description.property_id,
                self.entity_description.property_type,
            )
        )
        await self._update_constraints()

    async def async_set_native_value(self, value: float) -> None:
        """Set the configured property value."""
        encoded_value = round(value * self.entity_description.scale)

        if self.entity_description.speed:
            await self._ccb.set_flow_for_speed(self.entity_description.speed, encoded_value)
        else:
            await self._ccb.set_property_typed(
                self.entity_description.unit,
                self.entity_description.subunit,
                self.entity_description.property_id,
                encoded_value,
                self.entity_description.property_type,
            )

        self._attr_native_value = value

    async def _update_constraints(self) -> None:
        """Read min, max, and step metadata from the ventilation unit."""
        range_data = await self._read_property_metadata(PROPERTY_RANGE)
        if len(range_data) >= 2:
            self._attr_native_min_value = self._decode_value(range_data[0])
            self._attr_native_max_value = self._decode_value(range_data[1])

        step_data = await self._read_property_metadata(PROPERTY_STEP)
        if step_data:
            self._attr_native_step = self._decode_value(step_data[0])

    async def _read_property_metadata(self, kind: int) -> list[int]:
        """Read typed property metadata values from the bridge."""
        result = await self._ccb.cmd_rmi_request(
            bytes(
                [
                    0x01,
                    self.entity_description.unit,
                    self.entity_description.subunit,
                    kind,
                    self.entity_description.property_id,
                ]
            )
        )
        data = bytes(result.message)
        if len(data) % 2:
            return []
        return [int.from_bytes(data[index : index + 2], byteorder="little", signed=True) for index in range(0, len(data), 2)]

    def _decode_value(self, value: int) -> float:
        """Decode raw property values to their native Home Assistant value."""
        return value / self.entity_description.scale
