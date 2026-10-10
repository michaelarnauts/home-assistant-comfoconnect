"""Boost duration is a saved preference and activity is confirmed by the unit."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY
from custom_components.comfoconnect.binary_sensor import ComfoConnectBoostStatus
from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.select import ComfoConnectBoostDuration
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.restore_state import RestoreStateData
from homeassistant.helpers.restore_state import async_load as setup_restore_state
from homeassistant.loader import async_setup as setup_loader


def test_duration_start_stop_and_device_status(tmp_path):
    """Changing duration sends no command; buttons use it and status reads the unit."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        await setup_restore_state(hass)
        await er.async_load(hass)
        await dr.async_load(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, boost_duration=3600, set_boost=AsyncMock(), get_boost=AsyncMock(return_value=False))
        duration = ComfoConnectBoostDuration(bridge)
        duration_component = EntityComponent(logging.getLogger(__name__), "select", hass)
        await duration_component.async_add_entities([duration])
        status = ComfoConnectBoostStatus(bridge)
        status_component = EntityComponent(logging.getLogger(__name__), "binary_sensor", hass)
        await status_component.async_add_entities([status], update_before_add=True)
        buttons = [
            ComfoConnectButton(bridge, SimpleNamespace(), next(item for item in BUTTON_TYPES if item.key == key))
            for key in ("start_boost", "cancel_boost")
        ]
        button_component = EntityComponent(logging.getLogger(__name__), "button", hass)
        await button_component.async_add_entities(buttons)

        assert duration.current_option == "60 Minutes"
        assert status.is_on is False
        await duration.async_select_option("20 Minutes")
        bridge.set_boost.assert_not_awaited()
        await buttons[0].async_press()
        bridge.set_boost.assert_awaited_once_with(True, 1200)
        assert status.is_on is False
        bridge.get_boost.return_value = True
        await status.async_update_ha_state(force_refresh=True)
        assert hass.states.get(status.entity_id).state == "on"
        assert hass.states.get(duration.entity_id).state == "20 Minutes"

        # Changing the next duration must not extend a boost already running.
        await duration.async_select_option("40 Minutes")
        assert bridge.set_boost.await_count == 1
        await buttons[1].async_press()
        assert bridge.set_boost.await_args.args == (False,)
        assert status.is_on is True
        bridge.get_boost.return_value = False
        await status.async_update_ha_state(force_refresh=True)
        assert hass.states.get(status.entity_id).state == "off"
        assert duration.current_option == "40 Minutes"

        async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), False)
        await hass.async_block_till_done()
        assert hass.states.get(status.entity_id).state == "unavailable"
        assert all(not button.available for button in buttons)
        assert hass.states.get(duration.entity_id).state == "40 Minutes"
        await duration_component.async_remove_entity(duration.entity_id)
        await status_component.async_remove_entity(status.entity_id)
        for button in buttons:
            await button_component.async_remove_entity(button.entity_id)
        await hass.async_stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "saved,expected,seconds", [("30 Minutes", "30 Minutes", 1800), ("unknown", "60 Minutes", 3600), ("Active", "60 Minutes", 3600)]
)
def test_duration_restore_and_invalid_state_fallback(tmp_path, saved, expected, seconds):
    """Use Home Assistant's restore lifecycle and reject old or invalid values."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        await setup_restore_state(hass)
        await er.async_load(hass)
        await dr.async_load(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, boost_duration=3600, set_boost=AsyncMock())
        original = ComfoConnectBoostDuration(bridge)
        original.entity_id = "select.boost_duration"
        component = EntityComponent(logging.getLogger(__name__), "select", hass)
        await component.async_add_entities([original])
        if saved in original.options:
            await original.async_select_option(saved)
        else:
            hass.states.async_set(original.entity_id, saved)
        await RestoreStateData.async_save_persistent_states(hass)
        await component.async_remove_entity(original.entity_id)
        await hass.async_stop()

        # Load the saved preference into a new Home Assistant instance.
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        await setup_restore_state(hass)
        await er.async_load(hass)
        await dr.async_load(hass)
        component = EntityComponent(logging.getLogger(__name__), "select", hass)
        bridge.boost_duration = 3600
        restored = ComfoConnectBoostDuration(bridge)
        restored.entity_id = original.entity_id
        await component.async_add_entities([restored])
        assert restored.current_option == expected
        assert bridge.boost_duration == seconds
        bridge.set_boost.assert_not_awaited()
        await component.async_remove_entity(restored.entity_id)
        await hass.async_stop()

    asyncio.run(scenario())


def test_failed_start_does_not_claim_boost_is_active(tmp_path):
    """A failed device command propagates without creating a false active state."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(
            uuid="test",
            is_available=True,
            boost_duration=3600,
            set_boost=AsyncMock(side_effect=TimeoutError),
            get_boost=AsyncMock(return_value=False),
        )
        status = ComfoConnectBoostStatus(bridge)
        await status.async_update()
        button = ComfoConnectButton(bridge, SimpleNamespace(), next(item for item in BUTTON_TYPES if item.key == "start_boost"))
        with pytest.raises(TimeoutError):
            await button.async_press()
        assert status.is_on is False
        await hass.async_stop()

    asyncio.run(scenario())
