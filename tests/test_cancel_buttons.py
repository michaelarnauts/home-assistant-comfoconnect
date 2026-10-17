"""The cancel buttons sit with the Boost and Away selects they belong to."""

import pytest
from custom_components.comfoconnect.button import BUTTON_TYPES
from custom_components.comfoconnect.select import SELECT_TYPES


@pytest.mark.parametrize(("button", "select"), [("cancel_boost", "boost_timeout"), ("cancel_away", "away_timeout")])
def test_cancel_buttons_are_controls_like_their_select(button: str, select: str) -> None:
    """Both are controls, so they show up in the same place on a dashboard."""
    button_description = next(item for item in BUTTON_TYPES if item.key == button)
    select_description = next(item for item in SELECT_TYPES if item.key == select)
    assert button_description.entity_category is None
    assert select_description.entity_category is None
