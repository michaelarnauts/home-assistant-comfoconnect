"""Test the button platform."""

from unittest.mock import ANY, MagicMock

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from custom_components.comfoconnect.const import DOMAIN
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the button platform."""
    return [Platform.BUTTON]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the button entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "method", "args"),
    [
        ("button.comfoairq_reset_errors", "clear_errors", ()),
        ("button.comfoairq_cancel_boost", "set_boost", (False,)),
        ("button.comfoairq_cancel_away", "set_away", (False,)),
    ],
)
async def test_press(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, entity_id: str, method: str, args: tuple
) -> None:
    """Test that pressing a button sends its command to the unit."""
    await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True)

    mock_comfoconnect[method].assert_awaited_once_with(ANY, *args)


async def test_press_failed(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that a press the unit doesn't answer raises an error."""
    mock_comfoconnect["set_boost"].side_effect = AioComfoConnectTimeout("No answer")

    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.comfoairq_cancel_boost"}, blocking=True)

    assert failure.value.translation_domain == DOMAIN
    assert failure.value.translation_key == "press_failed"
    assert failure.value.translation_placeholders["error"] == "No answer"
