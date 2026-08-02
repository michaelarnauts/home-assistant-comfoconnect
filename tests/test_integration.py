"""
Tests that the integration can be loaded, and that its manifest matches what it needs.

These don't test any behaviour yet, they make sure the integration imports at all. Home Assistant
imports every platform when it sets up the config entry, so a name that doesn't exist in the
version of aiocomfoconnect we pin takes the whole integration down at runtime, and neither ruff
nor the formatter can see that.
"""

from __future__ import annotations

import importlib
import json
import re
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

COMPONENT_PATH = Path(__file__).parent.parent / "custom_components" / "comfoconnect"
MANIFEST_PATH = COMPONENT_PATH / "manifest.json"
PYPROJECT_PATH = Path(__file__).parent.parent / "pyproject.toml"

# Every module of the integration, so a new platform is covered without touching this file.
MODULES = sorted(path.stem for path in COMPONENT_PATH.glob("*.py"))


@pytest.fixture(name="manifest")
def manifest_fixture() -> dict:
    """Return the parsed manifest."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", MODULES)
def test_module_can_be_imported(module: str) -> None:
    """Test that every module of the integration can be imported."""
    importlib.import_module(f"custom_components.comfoconnect.{module}")


def test_all_platforms_are_covered() -> None:
    """Test that the platforms the integration sets up are all present."""
    integration = importlib.import_module("custom_components.comfoconnect")

    for platform in integration.PLATFORMS:
        assert platform.value in MODULES


def test_manifest_has_what_home_assistant_needs(manifest: dict) -> None:
    """Test that the manifest has the keys Home Assistant requires from a custom integration."""
    for key in ("domain", "name", "documentation", "codeowners", "requirements", "version"):
        assert manifest.get(key), f"{key} is missing from the manifest"

    assert manifest["domain"] == "comfoconnect"


def test_manifest_version_matches_pyproject(manifest: dict) -> None:
    """Test that both places that carry our version agree, since a release has to bump both."""
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    assert manifest["version"] == pyproject["tool"]["poetry"]["version"]


def test_requirements_match_the_installed_library(manifest: dict) -> None:
    """
    Test that we import the library version we pin.

    The modules above are imported against whatever is installed, so this makes sure that is the
    version users get, instead of the tests passing against something newer than the pin.
    """
    for requirement in manifest["requirements"]:
        name, pinned = re.match(r"([\w-]+)==(.+)", requirement).groups()

        try:
            installed = version(name)
        except PackageNotFoundError:
            pytest.skip(f"{name} is not installed")

        assert installed == pinned, f"{name} {installed} is installed, but the manifest pins {pinned}"
