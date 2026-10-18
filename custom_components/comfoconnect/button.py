"""Button for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast

from aiocomfoconnect.exceptions import AioComfoConnectError
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ComfoConnectBridge, ComfoConnectConfigEntry
from .entity import ComfoConnectEntity

_LOGGER = logging.getLogger(__name__)

# One at a time: these entities poll or send commands, and the bridge doesn't like many requests at once.
PARALLEL_UPDATES = 1


@dataclass
class ComfoconnectRequiredKeysMixin:
    """Mixin for required keys."""

    press_fn: Callable[[ComfoConnectBridge, str], Awaitable[Any]]


@dataclass
class ComfoconnectButtonEntityDescription(ButtonEntityDescription, ComfoconnectRequiredKeysMixin):
    """Describes ComfoConnect button entity."""


BUTTON_TYPES = (
    ComfoconnectButtonEntityDescription(
        key="reset_errors",
        press_fn=lambda ccb, option: cast(Coroutine, ccb.clear_errors()),
        name="Reset errors",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectButtonEntityDescription(
        key="cancel_boost",
        press_fn=lambda ccb, option: cast(Coroutine, ccb.set_boost(False)),
        name="Cancel boost",
        icon="mdi:fan-off",
    ),
    ComfoconnectButtonEntityDescription(
        key="cancel_away",
        press_fn=lambda ccb, option: cast(Coroutine, ccb.set_away(False)),
        name="Cancel away",
        icon="mdi:home-import-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfoConnectConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect binary sensors."""
    ccb = config_entry.runtime_data

    sensors = [ComfoConnectButton(ccb=ccb, config_entry=config_entry, description=description) for description in BUTTON_TYPES]

    async_add_entities(sensors, True)


class ComfoConnectButton(ComfoConnectEntity, ButtonEntity):
    """Representation of a ComfoConnect button."""

    entity_description: ComfoconnectButtonEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ComfoConnectConfigEntry,
        description: ComfoconnectButtonEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        super().__init__(ccb)
        self.entity_description = description
        self._attr_name = f"{description.name}"
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"

    async def async_press(self) -> None:
        """Press the button."""
        try:
            await self.entity_description.press_fn(self._ccb, self._attr_unique_id)
        except AioComfoConnectError as err:
            raise HomeAssistantError(f"Failed to press {self.entity_description.name}: {err}") from err
