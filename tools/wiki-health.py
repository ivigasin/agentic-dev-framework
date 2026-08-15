#!/usr/bin/env python3
"""Entrypoint shim: `python3 tools/wiki-health.py [args]` from the repo root.

The filename is hyphenated and therefore not importable, so this file does
nothing but put its own directory on sys.path and hand off to the package.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wiki_health.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
