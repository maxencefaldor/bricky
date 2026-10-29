# Copyright 2026 Maxence Faldor
"""Configuration shared by every front end.

Each setting comes whole from the first source that sets it: explicit arguments,
``BRICKY_*`` environment variables, or the configuration file in the working directory.
That file is ``bricky.toml`` when there is one, or else the ``[tool.bricky]`` table of
``pyproject.toml``.
"""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Final, override

from pydantic import (
    Field,
    ModelWrapValidatorHandler,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
)

from bricky.errors import BrickyError

CONFIG_FILE: Final = Path("bricky.toml")
"""The configuration file that, when present, replaces ``[tool.bricky]``."""

PYPROJECT: Final = Path("pyproject.toml")
"""The project file whose ``[tool.bricky]`` table configures bricky otherwise."""

ALL: Final = "all"
"""The key that sets the level of every rule at once."""

RULE_NAME: Final = r"^[a-z]+(-[a-z]+)*$"
"""A rule's name: lowercase words joined by hyphens, such as ``floating-group``."""


class Level(StrEnum):
    """How a check reports a rule's diagnostics, by the names ty gives its levels."""

    ERROR = "error"
    WARN = "warn"
    IGNORE = "ignore"


type RuleKey = Annotated[str, StringConstraints(pattern=RULE_NAME)]
"""A rule's name, or ``all`` for every rule."""


class Settings(BaseSettings):
    """Settings shared by every front end."""

    model_config = SettingsConfigDict(
        env_prefix="BRICKY_",
        env_ignore_empty=True,
        extra="forbid",
    )

    max_diagnostics: int = Field(
        default=20, ge=1, description="Maximum number of diagnostics a report lists."
    )
    build_timeout: float = Field(
        default=60.0,
        gt=0,
        description="Seconds a build script may run before bricky stops it.",
    )
    output_limit: int = Field(
        default=20_000,
        ge=0,
        description="Characters kept from each of a build script's standard output "
        "and standard error.",
    )
    render_browser: Path | None = Field(
        default=None,
        description="Chromium executable for renders; "
        "Playwright's own browser when unset.",
    )
    catalog: Path | None = Field(
        default=None,
        description="Catalog file to use. When unset, bricky uses the catalog that "
        "`bricky catalog import` wrote to its data folder, or its sample catalog "
        "when there is none.",
    )
    clutch: float = Field(
        default=2.94,
        gt=0,
        description="Newtons that pull one stud out of its anti-stud: three contact "
        "points of 0.98 N, as StableLego measured.",
    )
    friction: float = Field(
        default=0.2,
        ge=0,
        description="Coefficient of friction between faces that press together, "
        "a cautious value for ABS.",
    )
    density: float = Field(
        default=0.54,
        gt=0,
        description="Grams per cubic centimeter of an element's body, hollows "
        "included; 0.54 fits the bricks StableLego weighed.",
    )
    safety_factor: float = Field(
        default=2.0,
        ge=1,
        description="Times a stud's clutch must exceed what it holds before the rule "
        "strained-studs leaves it out.",
    )
    rules: dict[RuleKey, Level] = Field(
        default_factory=dict,
        description="Level of each rule by name, or of every rule with 'all': error, "
        "warn or ignore. A rule's own entry overrides 'all', and rules left out keep "
        "their default level.",
    )

    @model_validator(mode="wrap")
    @classmethod
    def _name_the_source(
        cls, data: object, handler: ModelWrapValidatorHandler[Settings]
    ) -> Settings:
        """Raise a :class:`BrickyError` that names each invalid setting and its source.

        Raises:
            BrickyError: If a source sets a setting that does not exist, or an invalid
                value.
        """
        try:
            return handler(data)
        except ValidationError as error:
            raise BrickyError(_invalid(error)) from error

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read explicit values, then the environment, then the configuration file."""
        configuration = InitSettingsSource(settings_cls, _configuration())
        return (_FirstSet(settings_cls, (init_settings, env_settings, configuration)),)


class _FirstSet(PydanticBaseSettingsSource):
    """Several sources, each setting taken whole from the first source that sets it.

    pydantic-settings merges a table such as ``rules`` key by key across its sources.
    bricky takes a table whole from one source, as it takes any other setting.
    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        sources: tuple[PydanticBaseSettingsSource, ...],
    ) -> None:
        """Read ``sources``, the first one first."""
        super().__init__(settings_cls)
        self._sources = sources

    @override
    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        """Read nothing field by field: :meth:`__call__` reads every source at once."""
        return None, field_name, False

    @override
    def __call__(self) -> dict[str, Any]:
        """Return each setting from the first source that sets it.

        Raises:
            BrickyError: If a ``BRICKY_*`` variable holds a value that cannot be read.
        """
        values: dict[str, Any] = {}
        for source in reversed(self._sources):
            try:
                values.update(source())
            except SettingsError as error:
                raise BrickyError(str(error)) from error
        return values


def _configuration() -> dict[str, Any]:
    """Return the settings of the configuration file in the working directory.

    The file ``bricky.toml``, when there is one, replaces the ``[tool.bricky]`` table of
    ``pyproject.toml``, as ``ty.toml`` replaces ``[tool.ty]``.

    Raises:
        BrickyError: If the file is not valid TOML.
    """
    path = CONFIG_FILE if CONFIG_FILE.is_file() else PYPROJECT
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        message = f"{path}: {error}"
        raise BrickyError(message) from error
    return data if path == CONFIG_FILE else data.get("tool", {}).get("bricky", {})


def _invalid(error: ValidationError) -> str:
    """Name each invalid setting, what is wrong with it and the source that set it."""
    problems = []
    for problem in error.errors():
        names = [str(part) for part in problem["loc"] if part != "[key]"]
        name = names[0] if names else ""
        variable = f"BRICKY_{name.upper()}"
        if os.environ.get(variable) is not None:
            source = variable
        elif name in _configuration():
            source = str(CONFIG_FILE) if CONFIG_FILE.is_file() else str(PYPROJECT)
        else:
            source = "the arguments"
        what = (
            "no such setting"
            if problem["type"] == "extra_forbidden"
            else problem["msg"]
        )
        problems.append(f"{'.'.join(names)}: {what}, in {source}")
    return "invalid settings: " + "; ".join(problems)
