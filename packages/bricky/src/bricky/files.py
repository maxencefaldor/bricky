"""Reading and writing model files and their source maps.

A model file (``name.bricky.json``) holds the model and nothing else. Its source map
(``name.bricky.map.json``) records which build-script lines placed each element, and the SHA-256
of the model file it describes, so a stale map is detected and ignored rather than trusted.
"""

from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from bricky.errors import BrickyError
from bricky.model import Model
from bricky.provenance import Provenance, SourceMap, model_digest

SUFFIX: Final = ".bricky.json"
"""File suffix for models."""

SOURCE_MAP_SUFFIX: Final = ".bricky.map.json"
"""File suffix for source maps."""


def model_stem(path: Path) -> str:
    """Return a model file's name without its suffix: ``tower.bricky.json`` gives ``tower``."""
    name = path.name
    return name.removesuffix(SUFFIX) if name.endswith(SUFFIX) else path.stem


def source_map_path(model_path: Path) -> Path:
    """Return where the source map of a model file lives."""
    return model_path.with_name(model_stem(model_path) + SOURCE_MAP_SUFFIX)


def write_file(path: Path, data: bytes) -> Path:
    """Write an output file, creating its folder if needed, and return its path.

    Every file bricky writes goes through here: models, source maps, pictures and viewers.

    Raises:
        BrickyError: If the file cannot be written.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as error:
        message = f"cannot write {path}: {error.strerror or error}"
        raise BrickyError(message) from None
    return path


def load_model(path: Path) -> Model:
    """Read a model file.

    Raises:
        BrickyError: If the file is missing, cannot be read or is not a valid model.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        message = f"no such model file: {path}"
        raise BrickyError(message) from None
    except OSError as error:
        message = f"cannot read {path}: {error.strerror or error}"
        raise BrickyError(message) from None
    try:
        return Model.model_validate_json(data)
    except ValidationError as error:
        message = f"{path} is not a valid bricky model:\n{error}"
        raise BrickyError(message) from None


def save_model(model: Model, path: Path) -> None:
    """Write a model file as indented JSON.

    Raises:
        BrickyError: If the file cannot be written.
    """
    write_file(path, _json(model.model_dump_json(indent=2)))


def save_source_map(provenance: Provenance, *, script: Path, model_path: Path) -> Path:
    """Write the source map of a saved model file and return its path.

    Raises:
        BrickyError: If the model file cannot be read or the map cannot be written.
    """
    try:
        digest = model_digest(model_path.read_bytes())
    except OSError as error:
        message = f"cannot read {model_path}: {error.strerror or error}"
        raise BrickyError(message) from None
    source_map = SourceMap(script=script.as_posix(), model_sha256=digest, provenance=provenance)
    return write_file(source_map_path(model_path), _json(source_map.model_dump_json(indent=2)))


def load_source_map(model_path: Path) -> Provenance | None:
    """Return a model file's provenance, or ``None`` if it has no current source map.

    A map that is missing, unreadable or written for different model bytes is ignored:
    provenance only ever adds detail to a report.
    """
    path = source_map_path(model_path)
    try:
        source_map = SourceMap.model_validate_json(path.read_bytes())
        current = model_digest(model_path.read_bytes())
    except OSError, ValidationError:
        return None
    return source_map.provenance if source_map.model_sha256 == current else None


def model_schema() -> dict[str, Any]:
    """Return the JSON Schema of the model file format."""
    return Model.model_json_schema()


def _json(text: str) -> bytes:
    return (text + "\n").encode()
