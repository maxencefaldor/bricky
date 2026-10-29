# Copyright 2026 Maxence Faldor
"""Shared test setup: every test, and every process it starts, uses the sample catalog.

A machine that has imported the full BrickLink catalog would otherwise give different
search results and counts, so tests pin the catalog to the sample shipped with bricky.
"""

from __future__ import annotations

import os

from bricky.catalog import SAMPLE_CATALOG

os.environ["BRICKY_CATALOG"] = str(SAMPLE_CATALOG)
