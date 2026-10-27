"""Resolve a model against the catalog and place every element in world space."""

from dataclasses import dataclass
from functools import cache

from bricky.catalog import Catalog, Connector, Part
from bricky.geometry import Box, Pose, Rotation, Vec3
from bricky.model import Element, Instance, Model


@dataclass(frozen=True, slots=True)
class Placed:
    """An element resolved against the catalog, in world space."""

    uid: str
    """Instance ids then the element id, joined by ``/``, such as ``"bay2/e3"``."""

    part: Part
    color: int
    pose: Pose
    solids: tuple[Box, ...]
    connectors: tuple[Connector, ...]
    bounds: Box


@dataclass(frozen=True, slots=True)
class Unresolved:
    """An element whose part is not in the catalog."""

    uid: str
    part: str


@dataclass(frozen=True, slots=True)
class World:
    """Every element of a model, unfolded and placed in world space."""

    placed: tuple[Placed, ...]
    unresolved: tuple[Unresolved, ...]


@cache
def _rotation(name: str) -> Rotation:
    return Rotation.parse(name)


def _pose(rot: str, pos: tuple[int, int, int]) -> Pose:
    return Pose(_rotation(rot), Vec3(*pos))


def build_world(model: Model, catalog: Catalog) -> World:
    """Unfold every instance and place each element in world space."""
    placed: list[Placed] = []
    unresolved: list[Unresolved] = []

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
                unresolved.append(Unresolved(uid, element.part))
                continue
            pose = parent @ _pose(element.rot, element.pos)
            solids = tuple(box.transformed(pose) for box in part.solids)
            placed.append(
                Placed(
                    uid=uid,
                    part=part,
                    color=element.color,
                    pose=pose,
                    solids=solids,
                    connectors=tuple(c.transformed(pose) for c in part.connectors),
                    bounds=Box.bounding(solids),
                )
            )
        for instance in instances:
            component = model.components[instance.component]
            visit(
                component.elements,
                component.instances,
                parent @ _pose(instance.rot, instance.pos),
                f"{prefix}{instance.id}/",
            )

    visit(model.elements, model.instances, Pose(), "")
    return World(placed=tuple(placed), unresolved=tuple(unresolved))
