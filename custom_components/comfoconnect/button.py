"""Button for the ComfoConnect integration."""

from __future__ import annotations

from collections.abc import Awaitable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Callable, cast

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)


@dataclass
class ComfoconnectRequiredKeysMixin:
    """Mixin for required keys."""

    press_fn: Callable[[ComfoConnectBridge, str], Awaitable[Any]]


@dataclass
class ComfoconnectButtonEntityDescription(
    ButtonEntityDescription, ComfoconnectRequiredKeysMixin
):
    """Describes ComfoConnect button entity."""


BUTTON_TYPES = (
    ComfoconnectButtonEntityDescription(
        key="reset_errors",
        press_fn=lambda ccb, option: cast(Coroutine, ccb.clear_errors()),
        name="Reset errors",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect binary sensors."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        ComfoConnectButton(ccb=ccb, config_entry=config_entry, description=description)
        for description in BUTTON_TYPES
    ]

    async_add_entities(sensors, True)


class ComfoConnectButton(ButtonEntity):
    """Representation of a ComfoConnect button."""

    _attr_has_entity_name = True
    entity_description: ComfoconnectButtonEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoconnectButtonEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_name = f"{description.name}"
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.press_fn(self._ccb, self._attr_unique_id)
