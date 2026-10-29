# Copyright 2026 Maxence Faldor
"""Lots: each part in each color that a model needs, with a quantity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Lot:
    """One part in one color, and how many of it a model uses."""

    part: str
    """The part's BrickLink id, such as ``3001``."""

    color: int
    """The color's BrickLink id, such as ``5`` for Red."""

    quantity: int
    """How many elements of the model are this part in this color."""
