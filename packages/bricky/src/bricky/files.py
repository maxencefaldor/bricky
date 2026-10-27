"""Reading and writing model files."""

from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from bricky.errors import BrickyError
from bricky.model import Model

SUFFIX: Final = ".bricky.json"
"""File suffix for models."""


def load_model(path: Path) -> Model:
    """Read a model file.

    Raises:
        BrickyError: If the file is missing or is not a valid model.
    """
    try:
        return Model.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        msg = f"no such model file: {path}"
        raise BrickyError(msg) from None
    except ValidationError as error:
        msg = f"{path} is not a valid bricky model:\n{error}"
        raise BrickyError(msg) from None


def save_model(model: Model, path: Path) -> None:
    """Write a model file as indented JSON."""
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def model_schema() -> dict[str, Any]:
    """Return the JSON Schema of the model file format."""
    return Model.model_json_schema()
