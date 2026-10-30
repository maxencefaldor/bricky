# Copyright 2026 Maxence Faldor

from __future__ import annotations

from pathlib import Path

import pytest

from bricky import BrickyError, Level, Settings


def test_rules_come_from_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.bricky]\nclutch = 2.0\n\n[tool.bricky.rules]\nstrained-studs = "warn"\n'
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.clutch == 2.0
    assert settings.rules == {"strained-studs": Level.WARN}


def test_bricky_toml_replaces_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.bricky]\nclutch = 2.0\n")
    (tmp_path / "bricky.toml").write_text('[rules]\nall = "warn"\n')
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.clutch == 2.94
    assert settings.rules == {"all": Level.WARN}


def test_a_source_that_sets_rules_replaces_the_tables_below_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bricky.toml").write_text('[rules]\noverlap = "warn"\n')
    monkeypatch.chdir(tmp_path)
    assert Settings().rules == {"overlap": Level.WARN}
    monkeypatch.setenv("BRICKY_RULES", '{"all": "ignore"}')
    assert Settings().rules == {"all": Level.IGNORE}
    explicit = Settings(rules={"blocked-stud": Level.ERROR})
    assert explicit.rules == {"blocked-stud": Level.ERROR}


def test_invalid_settings_name_their_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "bricky.toml"
    config.write_text('[rules]\nOverlap = "warn"\n')
    with pytest.raises(BrickyError, match=r"rules\.Overlap: .*, in bricky\.toml"):
        Settings()
    config.write_text('profile = "physical"\n')
    with pytest.raises(BrickyError, match=r"profile: no such setting, in bricky\.toml"):
        Settings()
    config.unlink()
    monkeypatch.setenv("BRICKY_RULES", '{"overlap": "deny"}')
    with pytest.raises(BrickyError, match=r"rules\.overlap: .*, in BRICKY_RULES"):
        Settings()
    monkeypatch.delenv("BRICKY_RULES")
    with pytest.raises(BrickyError, match=r"clutch: .*, in the arguments"):
        Settings(clutch=-1)


def test_a_configuration_file_that_is_not_toml_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bricky.toml").write_text("[rules\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(BrickyError, match=r"^bricky\.toml: "):
        Settings()
