"""Resolve a model against the catalog and place every element in world space."""

from dataclasses import dataclass
from functools import cache

from bricky.catalog import Catalog, Connector, Part
from bricky.geometry import Box, Pose, Rotation, Solid, Vector
from bricky.model import Element, Instance, Model


@dataclass(frozen=True, slots=True)
class PlacedElement:
    """An element resolved against the catalog, in world space."""

    uid: str
    """Instance ids then the element id, joined by ``/``, such as ``"bay2/e3"``."""

    part: Part
    color: int
    pose: Pose
    solids: tuple[Solid, ...]
    connectors: tuple[Connector, ...]
    bounds: Box


@dataclass(frozen=True, slots=True)
class UnknownElement:
    """An element whose part the catalog cannot place: unknown, or without a shape."""

    uid: str
    part: str
    color: int


@dataclass(frozen=True, slots=True)
class World:
    """Every element of a model, unfolded and placed in world space."""

    elements: tuple[PlacedElement, ...]
    unknown: tuple[UnknownElement, ...]


@cache
def _rotation(name: str) -> Rotation:
    return Rotation.parse(name)


def _pose(rotation: str, position: tuple[int, int, int]) -> Pose:
    return Pose(_rotation(rotation), Vector(*position))


def build_world(model: Model, catalog: Catalog) -> World:
    """Unfold every instance and place each element in world space."""
    placed: list[PlacedElement] = []
    unknown: list[UnknownElement] = []

    def visit(
        elements: tuple[Element, ...],
        instances: tuple[Instance, ...],
        parent: Pose,
        prefix: str,
    ) -> None:
        for element in elements:
            uid = prefix + element.id
            part = catalog.part(element.part)
            if part is None:
                unknown.append(UnknownElement(uid, element.part, element.color))
                continue
            pose = parent @ _pose(element.rotation, element.position)
            solids = tuple(solid.transformed(pose) for solid in part.solids)
            placed.append(
                PlacedElement(
                    uid=uid,
                    part=part,
                    color=element.color,
                    pose=pose,
                    solids=solids,
                    connectors=tuple(c.transformed(pose) for c in part.connectors),
                    bounds=Box.bounding(solid.bounds for solid in solids),
                )
            )
        for instance in instances:
            component = model.components[instance.component]
            visit(
                component.elements,
                component.instances,
                parent @ _pose(instance.rotation, instance.position),
                f"{prefix}{instance.id}/",
            )

    visit(model.elements, model.instances, Pose(), "")
    return World(elements=tuple(placed), unknown=tuple(unknown))
