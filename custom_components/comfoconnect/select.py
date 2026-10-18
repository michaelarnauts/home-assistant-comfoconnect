"""Select for the ComfoConnect integration."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from aiocomfoconnect.const import (
    ComfoCoolMode,
    VentilationBalance,
    VentilationMode,
    VentilationSetting,
    VentilationTemperatureProfile,
)
from aiocomfoconnect.properties import (
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT,
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION,
    PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE,
    PROPERTY_TEMPERATURE_PROFILE_MODE,
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    DOMAIN,
    SIGNAL_COMFOCONNECT_AVAILABILITY,
    SIGNAL_COMFOCONNECT_UPDATE_RECEIVED,
    ComfoConnectBridge,
)

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
    # Poll less often than the platform's scan interval, for settings that hardly ever change.
    update_interval: timedelta | None = None


# Settings that are normally only changed during installation don't need to be polled every 30 seconds.
SETTING_UPDATE_INTERVAL = timedelta(minutes=5)

TIMER_OFF = "Off"
TIMER_ACTIVE = "Active"
TIMEOUT_OPTIONS = ("10 Minutes", "20 Minutes", "30 Minutes", "40 Minutes", "50 Minutes", "60 Minutes")
TIMER_OPTIONS = (TIMER_OFF, TIMER_ACTIVE, *TIMEOUT_OPTIONS)
AWAY_OPTIONS = (*TIMER_OPTIONS, "2 Hours", "8 Hours", "24 Hours", "7 Days", "14 Days")


def _timeout_seconds(option: str) -> int:
    """Convert a timeout option to seconds."""
    duration, unit = option.split()
    return int(duration) * {"Minutes": 60, "Hours": 3600, "Days": 86400}[unit]


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


async def _set_bypass_option(ccb: ComfoConnectBridge, option: str) -> None:
    """Set a bypass timer or restore automatic control."""
    if option == TIMER_OFF:
        await ccb.set_bypass(VentilationSetting.AUTO)
    elif option != TIMER_ACTIVE:
        await ccb.set_bypass(VentilationSetting.ON, _timeout_seconds(option))


async def _get_bypass_option(ccb: ComfoConnectBridge) -> str:
    """Return whether bypass is forced on."""
    return _timer_option(await ccb.get_bypass() == VentilationSetting.ON)


async def _get_temperature_profile_mode(ccb: ComfoConnectBridge) -> str | None:
    """Return the temperature profile mode, or None for a mode that isn't offered, like external setpoint (2)."""
    try:
        return await ccb.get_property(PROPERTY_TEMPERATURE_PROFILE_MODE)
    except ValueError:
        return None


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
            255: VentilationMode.AUTO,
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
        entity_registry_enabled_default=False,
        update_interval=SETTING_UPDATE_INTERVAL,
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
        key="temperature_profile_mode",
        name="Temperature Profile Mode",
        icon="mdi:thermometer-auto",
        entity_registry_enabled_default=False,
        update_interval=SETTING_UPDATE_INTERVAL,
        entity_category=EntityCategory.CONFIG,
        get_value_fn=_get_temperature_profile_mode,
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_property(PROPERTY_TEMPERATURE_PROFILE_MODE, option)),
        options=list(PROPERTY_TEMPERATURE_PROFILE_MODE.options.values()),
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
        get_value_fn=_get_away_option,
        set_value_fn=_set_away_option,
        options=list(AWAY_OPTIONS),
    ),
    ComfoconnectSelectEntityDescription(
        key="bypass_timeout",
        name="Bypass timer",
        icon="mdi:camera-iris",
        get_value_fn=_get_bypass_option,
        set_value_fn=_set_bypass_option,
        options=list(TIMER_OPTIONS),
        # The unit pushes 1 while bypass is forced on, also when a timer ends, so this doesn't need polling.
        sensor=SENSORS.get(SENSOR_BYPASS_ACTIVATION_STATE),
        sensor_value_fn=lambda value: TIMER_ACTIVE if value == 1 else TIMER_OFF,
    ),
    ComfoconnectSelectEntityDescription(
        key="sensor_ventmode_temperature_passive",
        name="Temperature sensor ventilation",
        icon="mdi:thermometer-auto",
        entity_registry_enabled_default=False,
        update_interval=SETTING_UPDATE_INTERVAL,
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_property(PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE)),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_property(PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE, option)),
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
        entity_registry_enabled_default=False,
        update_interval=SETTING_UPDATE_INTERVAL,
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_property(PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT)),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_property(PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT, option)),
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
        entity_registry_enabled_default=False,
        update_interval=SETTING_UPDATE_INTERVAL,
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_property(PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION)),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_property(PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION, option)),
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
        self._attr_should_poll = not description.sensor
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_available = ccb.is_available
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )
        self._last_update: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates and availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid),
                self._handle_availability_update,
            )
        )

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

    @callback
    def _handle_availability_update(self, available: bool) -> None:
        """Handle bridge availability changes."""
        self._attr_available = available
        self.async_write_ha_state()

    @callback
    def _handle_update(self, value):
        """Handle update callbacks."""
        _LOGGER.debug(
            "Handle update for sensor %s (%s): %s",
            self.entity_description.sensor.name,
            self.entity_description.sensor.id,
            value,
        )

        self._attr_current_option = self.entity_description.sensor_value_fn(value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the state."""
        interval = self.entity_description.update_interval
        if interval and self._last_update is not None and time.monotonic() - self._last_update < interval.total_seconds():
            return
        self._attr_current_option = await self.entity_description.get_value_fn(self._ccb)
        self._last_update = time.monotonic()

    async def async_select_option(self, option: str) -> None:
        """Set the selected option."""
        await self.entity_description.set_value_fn(self._ccb, option)
        if TIMER_ACTIVE in self.entity_description.options:
            if option == TIMER_ACTIVE:
                # Active only reports status; selecting it must not invent a timer.
                self._attr_current_option = await self.entity_description.get_value_fn(self._ccb)
            else:
                self._attr_current_option = TIMER_OFF if option == TIMER_OFF else TIMER_ACTIVE
        else:
            self._attr_current_option = option
        self.async_write_ha_state()
