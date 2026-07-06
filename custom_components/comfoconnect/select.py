"""Select for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Coroutine
from dataclasses import dataclass
from typing import Any, Callable, cast

from aiocomfoconnect.const import (
    ComfoCoolMode,
    VentilationBalance,
    VentilationMode,
    VentilationSetting,
    VentilationTemperatureProfile,
)
from aiocomfoconnect.sensors import (
    SENSOR_BYPASS_ACTIVATION_STATE,
    SENSOR_COMFOCOOL_STATE,
    SENSOR_OPERATING_MODE,
    SENSOR_PROFILE_TEMPERATURE,
    SENSORS,
)
from aiocomfoconnect.sensors import (
    Sensor as AioComfoConnectSensor,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)


@dataclass
class ComfoconnectSelectDescriptionMixin:
    """Mixin for required keys."""

    set_value_fn: Callable[[ComfoConnectBridge, str], Awaitable[Any]]
    get_value_fn: Callable[[ComfoConnectBridge], Awaitable[Any]]


@dataclass
class ComfoconnectSelectEntityDescription(SelectEntityDescription, ComfoconnectSelectDescriptionMixin):
    """Describes ComfoConnect select entity."""

    sensor: AioComfoConnectSensor = None
    sensor_value_fn: Callable[[str], Any] = None


TIMER_OFF = "Off"
TIMER_ACTIVE = "Active"
TIMEOUT_OPTIONS = ("10 Minutes", "20 Minutes", "30 Minutes", "40 Minutes", "50 Minutes", "60 Minutes")
TIMER_OPTIONS = (TIMER_OFF, TIMER_ACTIVE, *TIMEOUT_OPTIONS)


def _timeout_seconds(option: str) -> int:
    """Convert a timeout option to seconds."""
    return int(option.split()[0]) * 60


def _timer_option(active: bool) -> str:
    """Map a timer state to a select option."""
    return TIMER_ACTIVE if active else TIMER_OFF


async def _set_boost_option(ccb: ComfoConnectBridge, option: str) -> None:
    """Set or cancel boost mode from a select option."""
    if option == TIMER_OFF:
        await ccb.set_boost(False)
    elif option != TIMER_ACTIVE:
        await ccb.set_boost(True, _timeout_seconds(option))


async def _set_away_option(ccb: ComfoConnectBridge, option: str) -> None:
    """Set or cancel away mode from a select option."""
    if option == TIMER_OFF:
        await ccb.set_away(False)
    elif option != TIMER_ACTIVE:
        await ccb.set_away(True, _timeout_seconds(option))


async def _get_boost_option(ccb: ComfoConnectBridge) -> str:
    """Return the current boost select option."""
    return _timer_option(await ccb.get_boost())


async def _get_away_option(ccb: ComfoConnectBridge) -> str:
    """Return the current away select option."""
    return _timer_option(await ccb.get_away())


SELECT_TYPES = (
    ComfoconnectSelectEntityDescription(
        key="select_mode",
        name="Ventilation Mode",
        icon="mdi:fan-auto",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_mode()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_mode(option)),
        options=[VentilationMode.AUTO, VentilationMode.MANUAL],
        # translation_key="setting",
        sensor=SENSORS.get(SENSOR_OPERATING_MODE),
        sensor_value_fn=lambda value: {
            -1: VentilationMode.AUTO,
            1: VentilationMode.MANUAL,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="bypass_mode",
        name="Bypass Mode",
        icon="mdi:camera-iris",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_bypass()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_bypass(option)),
        options=[
            VentilationSetting.AUTO,
            VentilationSetting.ON,
            VentilationSetting.OFF,
        ],
        # translation_key="setting",
        sensor=SENSORS.get(SENSOR_BYPASS_ACTIVATION_STATE),
        sensor_value_fn=lambda value: {
            0: VentilationSetting.AUTO,
            1: VentilationSetting.ON,
            2: VentilationSetting.OFF,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="balance_mode",
        name="Balance Mode",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_balance_mode()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_balance_mode(option)),
        options=[
            VentilationBalance.BALANCE,
            VentilationBalance.SUPPLY_ONLY,
            VentilationBalance.EXHAUST_ONLY,
        ],
        # translation_key="balance",
    ),
    ComfoconnectSelectEntityDescription(
        key="temperature_profile",
        name="Temperature Profile",
        icon="mdi:thermometer-auto",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_temperature_profile()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_temperature_profile(option)),
        options=[
            VentilationTemperatureProfile.WARM,
            VentilationTemperatureProfile.NORMAL,
            VentilationTemperatureProfile.COOL,
        ],
        # translation_key="temperature_profile",
        sensor=SENSORS.get(SENSOR_PROFILE_TEMPERATURE),
        sensor_value_fn=lambda value: {
            0: VentilationTemperatureProfile.NORMAL,
            1: VentilationTemperatureProfile.COOL,
            2: VentilationTemperatureProfile.WARM,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="comfocool",
        name="ComfoCool Mode",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_comfocool_mode()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_comfocool_mode(option)),
        options=[
            ComfoCoolMode.AUTO,
            ComfoCoolMode.OFF,
        ],
        # translation_key="comfocool",
        sensor=SENSORS.get(SENSOR_COMFOCOOL_STATE),
        sensor_value_fn=lambda value: {
            0: ComfoCoolMode.OFF,
            1: ComfoCoolMode.AUTO,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="boost_timeout",
        name="Boost Mode",
        icon="mdi:fan-plus",
        get_value_fn=_get_boost_option,
        set_value_fn=_set_boost_option,
        options=list(TIMER_OPTIONS),
    ),
    ComfoconnectSelectEntityDescription(
        key="away_timeout",
        name="Away Mode",
        icon="mdi:home-export-outline",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=_get_away_option,
        set_value_fn=_set_away_option,
        options=list(TIMER_OPTIONS),
    ),
    ComfoconnectSelectEntityDescription(
        key="sensor_ventmode_temperature_passive",
        name="Temperature sensor ventilation",
        icon="mdi:thermometer-auto",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_sensor_ventmode_temperature_passive()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_sensor_ventmode_temperature_passive(option)),
        options=[
            VentilationSetting.AUTO,
            VentilationSetting.ON,
            VentilationSetting.OFF,
        ],
    ),
    ComfoconnectSelectEntityDescription(
        key="sensor_ventmode_humidity_comfort",
        name="Humidity comfort ventilation",
        icon="mdi:water-percent",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_sensor_ventmode_humidity_comfort()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_sensor_ventmode_humidity_comfort(option)),
        options=[
            VentilationSetting.AUTO,
            VentilationSetting.ON,
            VentilationSetting.OFF,
        ],
    ),
    ComfoconnectSelectEntityDescription(
        key="sensor_ventmode_humidity_protection",
        name="Humidity protection ventilation",
        icon="mdi:water-alert",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_sensor_ventmode_humidity_protection()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_sensor_ventmode_humidity_protection(option)),
        options=[
            VentilationSetting.AUTO,
            VentilationSetting.ON,
            VentilationSetting.OFF,
        ],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect selects."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    selects = [ComfoConnectSelect(ccb=ccb, config_entry=config_entry, description=description) for description in SELECT_TYPES]

    async_add_entities(selects, True)


class ComfoConnectSelect(SelectEntity):
    """Representation of a ComfoConnect select."""

    _attr_has_entity_name = True
    entity_description: ComfoconnectSelectEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoconnectSelectEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect select."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_should_poll = False if description.sensor else True
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        if not self.entity_description.sensor:
            return

        _LOGGER.debug(
            "Registering for sensor %s (%d)",
            self.entity_description.sensor.name,
            self.entity_description.sensor.id,
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self._ccb.uuid, self.entity_description.sensor.id),
                self._handle_update,
            )
        )
        await self._ccb.register_sensor(self.entity_description.sensor)

    def _handle_update(self, value):
        """Handle update callbacks."""
        _LOGGER.debug(
            "Handle update for sensor %s (%s): %s",
            self.entity_description.sensor.name,
            self.entity_description.sensor.id,
            value,
        )

        self._attr_current_option = self.entity_description.sensor_value_fn(value)
        self.schedule_update_ha_state()

    async def async_update(self) -> None:
        """Update the state."""
        self._attr_current_option = await self.entity_description.get_value_fn(self._ccb)

    async def async_select_option(self, option: str) -> None:
        """Set the selected option."""
        await self.entity_description.set_value_fn(self._ccb, option)
        self._attr_current_option = option
        self.schedule_update_ha_state()
