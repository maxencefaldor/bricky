# Copyright 2026 Maxence Faldor
"""Exact integer units for LEGO® System geometry.

bricky measures every length in *base units* of 0.4 mm, the largest length that divides
every System dimension exactly. Positions are therefore integers, and every check
compares integers.

Agents work in studs (x and y) and plates (z), never in base units. The helpers below
convert both ways and refuse values that land off the grid.
"""

from typing import Final

MM_PER_UNIT: Final = 0.4
"""Millimeters per base unit."""

STUD: Final = 20
"""Stud pitch: 8.0 mm."""

PLATE: Final = 8
"""Plate height: 3.2 mm."""

BRICK: Final = 3 * PLATE
"""Brick height: 9.6 mm, three plates."""

STUD_DIAMETER: Final = 12
"""Stud diameter: 4.8 mm."""

STUD_HEIGHT: Final = 4
"""Stud height: 1.7 mm in reality, rounded down to 1.6 mm to stay on the grid."""

_TOLERANCE: Final = 1e-9


def _exact(value: float, scale: int, unit: str) -> int:
    scaled = value * scale
    rounded = round(scaled)
    if abs(scaled - rounded) > _TOLERANCE:
        message = f"{value} {unit} is not a whole number of 0.4 mm base units"
        raise ValueError(message)
    return rounded


def studs(value: float) -> int:
    """Convert a horizontal length in studs to base units.

    Raises:
        ValueError: If the length is not a whole number of base units.
    """
    return _exact(value, STUD, "studs")


def plates(value: float) -> int:
    """Convert a height in plates to base units.

    Raises:
        ValueError: If the height is not a whole number of base units.
    """
    return _exact(value, PLATE, "plates")


def to_studs(units: int) -> float:
    """Convert a horizontal length in base units to studs."""
    return units / STUD


def to_plates(units: int) -> float:
    """Convert a height in base units to plates."""
    return units / PLATE
