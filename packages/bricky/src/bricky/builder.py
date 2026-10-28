"""Write models in agent-friendly coordinates.

Coordinates are ``(x, y, z)``: x points east and y north, both in studs, and z points up, in
plates. ``at`` always names the minimum corner of the rotated bounding box of whatever is placed,
a single part or a whole component, so rotating something never moves the corner of its footprint.

The builder also records which line of the build script made each placement (see
:mod:`bricky.provenance`), so diagnostics and renders can point back at it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from bricky.catalog import Catalog, default_catalog
from bricky.geometry import ORIGIN, Box, Pose, Rotation, Vector
from bricky.model import Component, Element, Identifier, Instance, Model
from bricky.provenance import Provenance, ScopeSources, Source, capture
from bricky.units import plates, studs

type Coordinates = Sequence[float]
"""``(x, y, z)`` with x and y in studs and z in plates."""

_IDENTIFIER: Final = TypeAdapter(Identifier)


def to_base_units(at: Coordinates) -> Vector:
    """Convert coordinates in studs, studs and plates to base units.

    Raises:
        ValueError: If the point does not have three coordinates or lands off the grid.
    """
    try:
        x, y, z = at
    except ValueError:
        message = f"expected (x, y, z), got {tuple(at)!r}"
        raise ValueError(message) from None
    return Vector(studs(x), studs(y), plates(z))


@dataclass(frozen=True, slots=True)
class _PendingInstance:
    """An instance whose position waits for its component's bounding box."""

    id: str
    component: str
    rotation: Rotation
    corner: Vector


class _Scope:
    """The elements and instances of the model or of one component, with their sources."""

    def __init__(self, catalog: Catalog, label: str) -> None:
        self.catalog = catalog
        self.label = label
        self.elements: list[Element] = []
        self.extents: list[Box] = []
        self.instances: list[_PendingInstance] = []
        self.ids: set[str] = set()
        self.element_sources: dict[str, Source] = {}
        self.instance_sources: dict[str, Source] = {}

    def place(
        self, part: str, at: Coordinates, color: int | str, rotation: str, id: str | None
    ) -> str:
        definition = self.catalog.part(part)
        if definition is None:
            entry = self.catalog.entry(part)
            if entry is None:
                message = f"unknown part {part!r}; search the catalog with `bricky parts <words>`"
            else:
                message = (
                    f"part {part} ({entry.name}) has no shape in bricky yet, so it cannot be "
                    "placed; `bricky parts <words>` lists parts that can be"
                )
            raise ValueError(message)
        parsed = Rotation.parse(rotation)
        footprint = Box(ORIGIN, definition.size).transformed(Pose(parsed))
        corner = to_base_units(at)
        color_id = self.catalog.resolve_color(color).id
        element = Element(
            id=self.claim(id, "e"),
            part=definition.id,
            color=color_id,
            rotation=parsed.name,
            position=(corner - footprint.min).as_tuple(),
        )
        self.elements.append(element)
        self.extents.append(Box(corner, corner + footprint.size))
        self.record(self.element_sources, element.id)
        return element.id

    def instance(self, component: str, at: Coordinates, rotation: str, id: str | None) -> str:
        pending = _PendingInstance(
            id=self.claim(id, "i"),
            component=component,
            rotation=Rotation.parse(rotation),
            corner=to_base_units(at),
        )
        self.instances.append(pending)
        self.record(self.instance_sources, pending.id)
        return pending.id

    def claim(self, id: str | None, prefix: str) -> str:
        """Claim an id in this scope: the one given, or the next free one with the prefix."""
        if id is not None:
            _IDENTIFIER.validate_python(id)
            if id in self.ids:
                message = f"id {id!r} is already used in {self.label}"
                raise ValueError(message)
        else:
            number = len(self.ids) + 1
            while f"{prefix}{number}" in self.ids:
                number += 1
            id = f"{prefix}{number}"
        self.ids.add(id)
        return id

    @staticmethod
    def record(table: dict[str, Source], key: str) -> None:
        source = capture()
        if source is not None:
            table[key] = source

    def resolve(
        self, boxes: Mapping[str, Box]
    ) -> tuple[tuple[Element, ...], tuple[Instance, ...], Box | None]:
        """Position every instance by its component's box and return the scope's contents.

        Returns the elements, the instances and the scope's bounding box, or ``None`` for the box
        when the scope is empty.
        """
        instances: list[Instance] = []
        extents = list(self.extents)
        for pending in self.instances:
            box = boxes.get(pending.component)
            if box is None:
                message = (
                    f"instance {pending.id!r} in {self.label} "
                    f"places unknown component {pending.component!r}"
                )
                raise ValueError(message)
            rotated = box.transformed(Pose(pending.rotation))
            instances.append(
                Instance(
                    id=pending.id,
                    component=pending.component,
                    rotation=pending.rotation.name,
                    position=(pending.corner - rotated.min).as_tuple(),
                )
            )
            extents.append(Box(pending.corner, pending.corner + rotated.size))
        bounds = Box.bounding(extents) if extents else None
        return tuple(self.elements), tuple(instances), bounds

    def sources(self) -> ScopeSources:
        return ScopeSources(
            elements=dict(self.element_sources), instances=dict(self.instance_sources)
        )


class _Placer:
    """The placing methods shared by models and components."""

    _scope: _Scope

    def place(
        self,
        part: str,
        at: Coordinates,
        *,
        color: int | str,
        rotation: str = "R0",
        id: str | None = None,
    ) -> str:
        """Place a part and return the element's id.

        Args:
            part: BrickLink item number, such as ``"3001"``, or another number of the part.
            at: Minimum corner of the rotated part, ``(x, y, z)`` in studs, studs and plates.
            color: BrickLink color id or name, such as ``"Red"``.
            rotation: Grid rotation, such as ``"R90"`` or ``"+y-x"``.
            id: The element's id; generated when omitted.

        Raises:
            ValueError: If the part, color, rotation, coordinates or id is invalid.
        """
        return self._scope.place(part, at, color, rotation, id)

    def instance(
        self, component: str, at: Coordinates, *, rotation: str = "R0", id: str | None = None
    ) -> str:
        """Place a copy of a component and return the instance's id.

        Args:
            component: Name given to :meth:`ModelBuilder.component`.
            at: Minimum corner of the rotated component's bounding box, ``(x, y, z)`` in studs,
                studs and plates, exactly as for :meth:`place`.
            rotation: Grid rotation, such as ``"R90"``.
            id: The instance's id; generated when omitted.

        Raises:
            ValueError: If the rotation, coordinates or id is invalid. Unknown and empty
                components are reported by :meth:`ModelBuilder.build`.
        """
        return self._scope.instance(component, at, rotation, id)


class ComponentBuilder(_Placer):
    """Collects the contents of one reusable component."""

    def __init__(self, scope: _Scope) -> None:
        self._scope = scope


class ModelBuilder(_Placer):
    """Build a model in agent-friendly coordinates.

    Example:
        >>> builder = ModelBuilder("wall")
        >>> builder.place("3001", at=(0, 0, 0), color="Red")
        'e1'
        >>> builder.place("3001", at=(0, 2, 3), color="Red", rotation="R90")
        'e2'
        >>> builder.build().element_count()
        2
    """

    def __init__(self, name: str = "model", *, catalog: Catalog | None = None) -> None:
        self._catalog = catalog or default_catalog()
        self._name = name
        self._scope = _Scope(self._catalog, "the model")
        self._components: dict[str, _Scope] = {}

    @property
    def catalog(self) -> Catalog:
        """The catalog this builder resolves parts and colors against."""
        return self._catalog

    def component(self, name: str) -> ComponentBuilder:
        """Start a reusable component and return the builder that fills it.

        Components may be filled in any order, before or after their instances are placed.

        Raises:
            ValueError: If a component with this name already exists.
        """
        if name in self._components:
            message = f"component {name!r} already exists"
            raise ValueError(message)
        scope = _Scope(self._catalog, f"component {name!r}")
        self._components[name] = scope
        return ComponentBuilder(scope)

    def build(self) -> Model:
        """Return the finished model.

        Raises:
            ValueError: If an instance places an unknown or empty component, or if components place
                each other in a cycle.
        """
        boxes: dict[str, Box] = {}
        built: dict[str, Component] = {}
        for name in self._dependency_order():
            elements, instances, bounds = self._components[name].resolve(boxes)
            if bounds is None:
                message = f"component {name!r} is empty: place at least one part in it"
                raise ValueError(message)
            boxes[name] = bounds
            built[name] = Component(elements=elements, instances=instances)
        elements, instances, _ = self._scope.resolve(boxes)
        return Model(
            name=self._name,
            elements=elements,
            instances=instances,
            components={name: built[name] for name in self._components},
        )

    def provenance(self) -> Provenance:
        """Return where the build script placed every element and instance so far."""
        return Provenance(
            model=self._scope.sources(),
            components={name: scope.sources() for name, scope in self._components.items()},
        )

    def _dependency_order(self) -> list[str]:
        """Order components so each comes after every component it places."""
        order: list[str] = []
        done: set[str] = set()

        def visit(name: str, path: tuple[str, ...]) -> None:
            if name in done:
                return
            if name in path:
                cycle = " -> ".join((*path[path.index(name) :], name))
                message = f"components place each other in a cycle: {cycle}"
                raise ValueError(message)
            scope = self._components.get(name)
            if scope is None:
                return  # reported by resolve(), with the instance that names it
            for pending in scope.instances:
                visit(pending.component, (*path, name))
            done.add(name)
            order.append(name)

        for name in self._components:
            visit(name, ())
        return order
