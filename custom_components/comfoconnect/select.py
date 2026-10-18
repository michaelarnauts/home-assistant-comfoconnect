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
from aiocomfoconnect.exceptions import AioComfoConnectError
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
    SENSOR_PRESET_TIMERS,
    SENSOR_PROFILE_TEMPERATURE,
    SENSORS,
)
from aiocomfoconnect.sensors import (
    Sensor as AioComfoConnectSensor,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    SIGNAL_COMFOCONNECT_UPDATE_RECEIVED,
    ComfoConnectBridge,
    ComfoConnectConfigEntry,
)
from .entity import ComfoConnectEntity

_LOGGER = logging.getLogger(__name__)

# One at a time: these entities poll or send commands, and the bridge doesn't like many requests at once.
PARALLEL_UPDATES = 1


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

TIMER_OFF = "off"
TIMER_ACTIVE = "active"
# A timer option is its duration in minutes.
TIMEOUT_OPTIONS = ("10", "20", "30", "40", "50", "60")
TIMER_OPTIONS = (TIMER_OFF, TIMER_ACTIVE, *TIMEOUT_OPTIONS)
# Away also offers 2, 8 and 24 hours, and 7 and 14 days.
AWAY_OPTIONS = (*TIMER_OPTIONS, "120", "480", "1440", "10080", "20160")

# Bits of the running timers in SENSOR_PRESET_TIMERS.
BOOST_TIMER_BIT = 1 << 6
AWAY_TIMER_BIT = 1 << 11


def _timer_option(active: bool) -> str:
    """Map a timer state to a select option."""
    return TIMER_ACTIVE if active else TIMER_OFF


async def _set_boost_option(ccb: ComfoConnectBridge, option: str) -> None:
    """Set or cancel boost mode from a select option."""
    if option == TIMER_OFF:
        await ccb.set_boost(False)
    elif option != TIMER_ACTIVE:
        await ccb.set_boost(True, int(option) * 60)


async def _set_away_option(ccb: ComfoConnectBridge, option: str) -> None:
    """Set or cancel away mode from a select option."""
    if option == TIMER_OFF:
        await ccb.set_away(False)
    elif option != TIMER_ACTIVE:
        await ccb.set_away(True, int(option) * 60)


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
        await ccb.set_bypass(VentilationSetting.ON, int(option) * 60)


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
        translation_key="select_mode",
        icon="mdi:fan-auto",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_mode()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_mode(option)),
        options=[VentilationMode.AUTO, VentilationMode.MANUAL],
        sensor=SENSORS.get(SENSOR_OPERATING_MODE),
        sensor_value_fn=lambda value: {
            255: VentilationMode.AUTO,
            1: VentilationMode.MANUAL,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="bypass_mode",
        translation_key="bypass_mode",
        icon="mdi:camera-iris",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_bypass()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_bypass(option)),
        options=[
            VentilationSetting.AUTO,
            VentilationSetting.ON,
            VentilationSetting.OFF,
        ],
        sensor=SENSORS.get(SENSOR_BYPASS_ACTIVATION_STATE),
        sensor_value_fn=lambda value: {
            0: VentilationSetting.AUTO,
            1: VentilationSetting.ON,
            2: VentilationSetting.OFF,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="balance_mode",
        translation_key="balance_mode",
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
    ),
    ComfoconnectSelectEntityDescription(
        key="temperature_profile",
        translation_key="temperature_profile",
        icon="mdi:thermometer-auto",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_temperature_profile()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_temperature_profile(option)),
        options=[
            VentilationTemperatureProfile.WARM,
            VentilationTemperatureProfile.NORMAL,
            VentilationTemperatureProfile.COOL,
        ],
        sensor=SENSORS.get(SENSOR_PROFILE_TEMPERATURE),
        sensor_value_fn=lambda value: {
            0: VentilationTemperatureProfile.NORMAL,
            1: VentilationTemperatureProfile.COOL,
            2: VentilationTemperatureProfile.WARM,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="temperature_profile_mode",
        translation_key="temperature_profile_mode",
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
        translation_key="comfocool",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=lambda ccb: cast(Coroutine, ccb.get_comfocool_mode()),
        set_value_fn=lambda ccb, option: cast(Coroutine, ccb.set_comfocool_mode(option)),
        options=[
            ComfoCoolMode.AUTO,
            ComfoCoolMode.OFF,
        ],
        sensor=SENSORS.get(SENSOR_COMFOCOOL_STATE),
        sensor_value_fn=lambda value: {
            0: ComfoCoolMode.OFF,
            1: ComfoCoolMode.AUTO,
        }.get(value),
    ),
    ComfoconnectSelectEntityDescription(
        key="boost_timeout",
        translation_key="boost_timeout",
        icon="mdi:fan-plus",
        get_value_fn=_get_boost_option,
        set_value_fn=_set_boost_option,
        options=list(TIMER_OPTIONS),
        # The unit pushes the running timers when one starts or ends, so this doesn't need polling.
        sensor=SENSORS.get(SENSOR_PRESET_TIMERS),
        sensor_value_fn=lambda value: _timer_option(bool(value & BOOST_TIMER_BIT)),
    ),
    ComfoconnectSelectEntityDescription(
        key="away_timeout",
        translation_key="away_timeout",
        icon="mdi:home-export-outline",
        get_value_fn=_get_away_option,
        set_value_fn=_set_away_option,
        options=list(AWAY_OPTIONS),
        sensor=SENSORS.get(SENSOR_PRESET_TIMERS),
        sensor_value_fn=lambda value: _timer_option(bool(value & AWAY_TIMER_BIT)),
    ),
    ComfoconnectSelectEntityDescription(
        key="bypass_timeout",
        translation_key="bypass_timeout",
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
        translation_key="sensor_ventmode_temperature_passive",
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
        translation_key="sensor_ventmode_humidity_comfort",
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
        translation_key="sensor_ventmode_humidity_protection",
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
    config_entry: ComfoConnectConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect selects."""
    ccb = config_entry.runtime_data

    selects = [ComfoConnectSelect(ccb=ccb, config_entry=config_entry, description=description) for description in SELECT_TYPES]

    async_add_entities(selects, True)


class ComfoConnectSelect(ComfoConnectEntity, SelectEntity):
    """Representation of a ComfoConnect select."""

    entity_description: ComfoconnectSelectEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ComfoConnectConfigEntry,
        description: ComfoconnectSelectEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect select."""
        super().__init__(ccb)
        self.entity_description = description
        self._attr_should_poll = not description.sensor
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._last_update: float | None = None

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates and availability changes."""
        await super().async_added_to_hass()

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
        # The bridge is reconnecting; the availability signal updates the entity.
        if not self._ccb.is_available:
            return
        try:
            self._attr_current_option = await self.entity_description.get_value_fn(self._ccb)
        except AioComfoConnectError as err:
            _LOGGER.warning("Could not update %s: %s", self.entity_id, err)
            return
        self._last_update = time.monotonic()

    async def async_select_option(self, option: str) -> None:
        """Set the selected option."""
        try:
            await self.entity_description.set_value_fn(self._ccb, option)
            if TIMER_ACTIVE in self.entity_description.options:
                if option == TIMER_ACTIVE:
                    # Active only reports status; selecting it must not invent a timer.
                    current_option = await self.entity_description.get_value_fn(self._ccb)
                else:
                    current_option = TIMER_OFF if option == TIMER_OFF else TIMER_ACTIVE
            else:
                current_option = option
        except AioComfoConnectError as err:
            raise HomeAssistantError(f"Failed to set {self.name}: {err}") from err
        self._attr_current_option = current_option
        self.async_write_ha_state()
