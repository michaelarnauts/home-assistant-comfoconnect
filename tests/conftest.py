"""Pytest configuration."""

import sys
from pathlib import Path

# Make custom_components importable, since it isn't installed as a package.
sys.path.insert(0, str(Path(__file__).parent.parent))
