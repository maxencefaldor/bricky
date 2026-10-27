"""Write models in agent-friendly coordinates.

Coordinates are ``(x, y, z)``: x points east and y north, both in studs, and z points up, in
plates. When placing a part, ``at`` is the minimum corner of the part's rotated bounding box, so
turning a part never moves the corner of its footprint.
"""

from collections.abc import Sequence

from bricky.catalog import Catalog, default_catalog
from bricky.geometry import ORIGIN, Box, Pose, Rotation, Vec3
from bricky.model import Component, Element, Instance, Model
from bricky.units import plates, studs

type Point = Sequence[float]
"""``(x, y, z)`` with x and y in studs and z in plates."""


def to_units(at: Point) -> Vec3:
    """Convert a point in studs, studs and plates to base units.

    Raises:
        ValueError: If the point does not have three coordinates or lands off the grid.
    """
    try:
        x, y, z = at
    except ValueError:
        msg = f"expected (x, y, z), got {tuple(at)!r}"
        raise ValueError(msg) from None
    return Vec3(studs(x), studs(y), plates(z))


class _Scope:
    """Elements and instances being collected for the model or one component."""

    def __init__(self, catalog: Catalog, label: str) -> None:
        self._catalog = catalog
        self._label = label
        self._elements: list[Element] = []
        self._instances: list[Instance] = []
        self._ids: set[str] = set()

    def place(
        self,
        part: str,
        at: Point,
        *,
        color: int | str,
        rot: str = "R0",
        name: str | None = None,
    ) -> str:
        """Place a part and return its id.

        Args:
            part: BrickLink item number, such as ``"3001"``.
            at: Minimum corner of the rotated part, ``(x, y, z)`` in studs, studs and plates.
            color: BrickLink colour id or name, such as ``"Red"``.
            rot: Grid rotation, such as ``"R90"`` or ``"+y-x"``.
            name: Element id; generated when omitted.

        Raises:
            ValueError: If the part, colour, rotation or position is invalid.
        """
        definition = self._catalog.part(part)
        if definition is None:
            msg = f"unknown part {part!r}; search the catalog with `bricky parts <words>`"
            raise ValueError(msg)
        rotation = Rotation.parse(rot)
        footprint = Box(ORIGIN, definition.size).transformed(Pose(rotation))
        pos = to_units(at) - footprint.lo
        element = Element(
            id=self._claim(name, "e"),
            part=part,
            color=self._catalog.resolve_color(color).id,
            rot=rotation.name,
            pos=pos.as_tuple(),
        )
        self._elements.append(element)
        return element.id

    def instance(
        self, component: str, at: Point, *, rot: str = "R0", name: str | None = None
    ) -> str:
        """Place a copy of a component, putting its origin at ``at``, and return its id.

        Raises:
            ValueError: If the rotation or position is invalid. Unknown components are reported
                when the model is built.
        """
        instance = Instance(
            id=self._claim(name, "i"),
            component=component,
            rot=Rotation.parse(rot).name,
            pos=to_units(at).as_tuple(),
        )
        self._instances.append(instance)
        return instance.id

    def _claim(self, name: str | None, prefix: str) -> str:
        if name is not None:
            if name in self._ids:
                msg = f"id {name!r} is already used in {self._label}"
                raise ValueError(msg)
        else:
            number = len(self._ids) + 1
            while f"{prefix}{number}" in self._ids:
                number += 1
            name = f"{prefix}{number}"
        self._ids.add(name)
        return name


class ComponentBuilder(_Scope):
    """Collects the contents of one reusable component."""

    def build(self) -> Component:
        """Return the component as collected so far."""
        return Component(elements=tuple(self._elements), instances=tuple(self._instances))


class ModelBuilder(_Scope):
    """Build a model in agent-friendly coordinates.

    Example:
        >>> builder = ModelBuilder("wall")
        >>> builder.place("3001", at=(0, 0, 0), color="Red")
        'e1'
        >>> builder.place("3001", at=(0, 2, 3), color="Red", rot="R90")
        'e2'
        >>> builder.build().element_count()
        2
    """

    def __init__(self, name: str = "model", *, catalog: Catalog | None = None) -> None:
        super().__init__(catalog or default_catalog(), "the model")
        self._name = name
        self._components: dict[str, ComponentBuilder] = {}

    def component(self, name: str) -> ComponentBuilder:
        """Start a reusable component and return the builder that fills it.

        Raises:
            ValueError: If a component with this name already exists.
        """
        if name in self._components:
            msg = f"component {name!r} already exists"
            raise ValueError(msg)
        builder = ComponentBuilder(self._catalog, f"component {name!r}")
        self._components[name] = builder
        return builder

    def build(self) -> Model:
        """Return the finished model.

        Raises:
            pydantic.ValidationError: If instances place unknown components or form a cycle.
        """
        return Model(
            name=self._name,
            elements=tuple(self._elements),
            instances=tuple(self._instances),
            components={name: builder.build() for name, builder in self._components.items()},
        )
