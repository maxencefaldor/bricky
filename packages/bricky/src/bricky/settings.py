# Copyright 2026 Maxence Faldor
"""Configuration shared by every front end.

Settings come, in order of precedence, from explicit arguments, ``BRICKY_*`` environment
variables and the ``[tool.bricky]`` table of the ``pyproject.toml`` in the working
directory.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final, override

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
)

from bricky.errors import BrickyError

DIGITAL: Final = ("schema", "collision", "connectivity")
"""Passes every model needs, whether or not anyone builds it for real."""

DEFAULT_PROFILES: Final[dict[str, tuple[str, ...]]] = {
    "digital": DIGITAL,
    "physical": (*DIGITAL, "stability", "buildability", "budget"),
}
"""Built-in profiles by name.

``physical`` adds passes that a physics pass pack provides.
"""


class Settings(BaseSettings):
    """Settings shared by every front end."""

    model_config = SettingsConfigDict(
        env_prefix="BRICKY_",
        env_ignore_empty=True,
        pyproject_toml_table_header=("tool", "bricky"),
        extra="ignore",
    )

    profile: str = Field(
        default="digital", description="Profile used when a command names none."
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
    profiles: dict[str, tuple[str, ...]] = Field(
        default_factory=lambda: dict(DEFAULT_PROFILES),
        description="Named pass lists; "
        "entries extend or override the built-in profiles.",
    )

    @field_validator("profiles", mode="after")
    @classmethod
    def _extend_defaults(
        cls, value: dict[str, tuple[str, ...]]
    ) -> dict[str, tuple[str, ...]]:
        return {**DEFAULT_PROFILES, **value}

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
        """Read explicit values, then the environment, then ``pyproject.toml``."""
        return (
            init_settings,
            env_settings,
            PyprojectTomlConfigSettingsSource(settings_cls),
        )

    def resolve_passes(
        self,
        profile: str | None = None,
        passes: Sequence[str] | None = None,
    ) -> tuple[str | None, tuple[str, ...]]:
        """Return the profile name and the passes to run.

        Explicit passes override any profile, and the profile name is then ``None``.
        Otherwise the named profile applies, or the default one.

        Raises:
            BrickyError: If the profile is unknown.
        """
        if passes is not None and len(passes) > 0:
            return None, tuple(passes)
        name = profile or self.profile
        try:
            return name, self.profiles[name]
        except KeyError:
            message = (
                f"unknown profile {name!r}; known profiles: {', '.join(self.profiles)}"
            )
            raise BrickyError(message) from None
