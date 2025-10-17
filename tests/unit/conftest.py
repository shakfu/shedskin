"""Pytest configuration for Shedskin unit tests."""

import sys
from pathlib import Path

# Add parent directory to path for imports
shedskin_root = Path(__file__).parent.parent
sys.path.insert(0, str(shedskin_root))
