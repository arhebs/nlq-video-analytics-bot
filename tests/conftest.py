"""Pytest configuration.

The repository uses a flat `src/` layout without an installed package. This conftest ensures tests
can import from the `src.*` namespace when running `pytest` locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure `import src...` works when running pytest without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
