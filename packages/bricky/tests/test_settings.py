# Copyright 2026 Maxence Faldor

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from bricky import Level, Settings


def test_rules_come_from_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.bricky]\nclutch = 2.0\n\n"
        '[tool.bricky.rules]\nstrained-studs = "ignore"\n'
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.clutch == 2.0
    assert settings.rules == {"strained-studs": Level.IGNORE}


def test_bricky_toml_replaces_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.bricky]\nclutch = 2.0\n")
    (tmp_path / "bricky.toml").write_text('[rules]\nall = "warn"\n')
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.clutch == 2.94
    assert settings.rules == {"all": Level.WARN}


def test_the_environment_overrides_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bricky.toml").write_text('[rules]\noverlap = "warn"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRICKY_RULES", '{"overlap": "ignore"}')
    assert Settings().rules == {"overlap": Level.IGNORE}


def test_levels_and_rule_names_are_validated() -> None:
    with pytest.raises(ValidationError, match="error', 'warn' or 'ignore'"):
        Settings.model_validate({"rules": {"overlap": "deny"}})
    with pytest.raises(ValidationError, match="should match pattern"):
        Settings.model_validate({"rules": {"Overlap": "warn"}})
