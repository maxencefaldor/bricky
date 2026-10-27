"""Configuration shared by every front-end.

Settings come, in order of precedence, from explicit arguments, ``BRICKY_*`` environment
variables and the ``[tool.bricky]`` table of the ``pyproject.toml`` in the working directory.
"""

from collections.abc import Sequence
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
"""Passes that every model needs, whether or not it will be built for real."""

DEFAULT_PROFILES: Final[dict[str, tuple[str, ...]]] = {
    "digital": DIGITAL,
    "physical": (*DIGITAL, "stability", "buildability", "budget"),
}
"""Built-in profiles. ``physical`` names passes that a physics plugin pack provides."""


class Settings(BaseSettings):
    """bricky settings."""

    model_config = SettingsConfigDict(
        env_prefix="BRICKY_",
        pyproject_toml_table_header=("tool", "bricky"),
        extra="ignore",
    )

    profile: str = Field(default="digital", description="Profile used when a command names none.")
    max_diagnostics: int = Field(default=20, ge=1, description="Diagnostics returned per check.")
    profiles: dict[str, tuple[str, ...]] = Field(
        default_factory=lambda: dict(DEFAULT_PROFILES),
        description="Named pass lists; entries extend or override the built-in profiles.",
    )

    @field_validator("profiles", mode="after")
    @classmethod
    def _extend_defaults(cls, value: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
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
        return (init_settings, env_settings, PyprojectTomlConfigSettingsSource(settings_cls))

    def resolve_passes(
        self,
        profile: str | None = None,
        passes: Sequence[str] | None = None,
    ) -> tuple[str | None, tuple[str, ...]]:
        """Return the profile name and the passes to run.

        Explicit passes win over any profile; otherwise the named or default profile applies.

        Raises:
            BrickyError: If the profile is unknown.
        """
        if passes:
            return None, tuple(passes)
        name = profile or self.profile
        try:
            return name, self.profiles[name]
        except KeyError:
            msg = f"unknown profile {name!r}; known profiles: {', '.join(self.profiles)}"
            raise BrickyError(msg) from None
