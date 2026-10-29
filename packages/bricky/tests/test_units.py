# Copyright 2026 Maxence Faldor

from __future__ import annotations

import pytest

from bricky.units import BRICK, PLATE, STUD, plates, studs, to_plates, to_studs


def test_system_dimensions_are_exact_in_base_units() -> None:
    assert (STUD, PLATE, BRICK) == (20, 8, 24)
    assert 5 * PLATE == 2 * STUD  # five plates stand as tall as two studs are wide


def test_conversions_round_trip() -> None:
    assert studs(2.5) == 50
    assert plates(3) == BRICK
    assert to_studs(studs(1.5)) == 1.5
    assert to_plates(plates(4)) == 4


def test_off_grid_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="not a whole number"):
        studs(0.01)
    with pytest.raises(ValueError, match="not a whole number"):
        plates(1 / 3)
