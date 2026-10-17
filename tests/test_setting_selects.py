"""Settings that hardly ever change are opt-in and polled less often."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.comfoconnect.select import SELECT_TYPES, SETTING_UPDATE_INTERVAL, ComfoConnectSelect

SETTINGS = (
    "balance_mode",
    "temperature_profile_mode",
    "sensor_ventmode_temperature_passive",
    "sensor_ventmode_humidity_comfort",
    "sensor_ventmode_humidity_protection",
)


@pytest.mark.parametrize("key", SETTINGS)
def test_setting_selects_are_opt_in_and_polled_less_often(key: str) -> None:
    """Each enabled poll is a request to the bridge, so these settings stay off by default."""
    description = next(item for item in SELECT_TYPES if item.key == key)
    assert description.entity_registry_enabled_default is False
    assert description.update_interval == SETTING_UPDATE_INTERVAL


async def test_a_setting_is_only_read_again_after_its_interval() -> None:
    """Polls within the update interval don't send a request."""
    description = next(item for item in SELECT_TYPES if item.key == "balance_mode")
    bridge = SimpleNamespace(uuid="test", is_available=True, get_balance_mode=AsyncMock(return_value="balance"))
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)

    with patch("custom_components.comfoconnect.select.time.monotonic", return_value=1000.0):
        await entity.async_update()
        await entity.async_update()
    assert bridge.get_balance_mode.await_count == 1
    assert entity.current_option == "balance"

    with patch("custom_components.comfoconnect.select.time.monotonic", return_value=1000.0 + SETTING_UPDATE_INTERVAL.total_seconds()):
        await entity.async_update()
    assert bridge.get_balance_mode.await_count == 2


async def test_timer_selects_keep_polling_every_scan() -> None:
    """Boost needs to show a running timer, so it's read on every poll."""
    description = next(item for item in SELECT_TYPES if item.key == "boost_timeout")
    assert description.update_interval is None
    bridge = SimpleNamespace(uuid="test", is_available=True, get_boost=AsyncMock(return_value=False))
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)

    await entity.async_update()
    await entity.async_update()
    assert bridge.get_boost.await_count == 2
