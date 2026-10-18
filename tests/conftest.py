"""Pytest configuration."""

import sys
from pathlib import Path

import pytest
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import PlatformData

# Make custom_components importable, since it isn't installed as a package.
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def entity_platform_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Let tests write the state of entities they create without a platform.

    An entity with a translation key needs platform data for its name. Entities that a platform adds get their own.
    """
    monkeypatch.setattr(Entity, "platform_data", PlatformData(None, domain="test", platform_name="comfoconnect"))
