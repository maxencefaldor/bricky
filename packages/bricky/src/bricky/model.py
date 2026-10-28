# Copyright 2026 Maxence Faldor
"""The canonical model format: what a build is, stored once.

A model is a small tree: top-level elements and instances, plus the named components that
instances place. The model refers to catalog parts and colors by id and never copies their data,
so analyses derive everything else, such as world geometry and connections. Positions are in
0.4 mm base units, and rotations use the grid rotation names of :mod:`bricky.geometry`.
"""

from collections.abc import Mapping, Sequence
from functools import cache
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from bricky.geometry import Rotation

FORMAT: Final = "bricky/1"
"""Format tag written into every model file."""


def _canonical_rotation(value: str) -> str:
    return Rotation.parse(value).name


type RotationName = Annotated[
    str,
    AfterValidator(_canonical_rotation),
    Field(
        description="Grid rotation, such as '+x+y' (the identity), '+y-x' or the alias 'R90'."
    ),
]
type Identifier = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9_.-]+$", description="Id, unique within its scope."),
]
type Position = Annotated[
    tuple[int, int, int],
    Field(description="Where the local origin lands, in 0.4 mm base units."),
]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Element(_Record):
    """One part in one color, placed in a model."""

    id: Identifier
    part: str = Field(description="Part id in the BrickLink catalog, such as '3001'.")
    color: int = Field(
        description="Color id in the BrickLink catalog, such as 5 (Red)."
    )
    rotation: RotationName = "+x+y"
    position: Position = (0, 0, 0)


class Instance(_Record):
    """One placed copy of a component."""

    id: Identifier
    component: str = Field(description="Name of the component to place.")
    rotation: RotationName = "+x+y"
    position: Position = (0, 0, 0)


class Component(_Record):
    """A group of elements and nested instances, stored once and placed by instances."""

    elements: tuple[Element, ...] = ()
    instances: tuple[Instance, ...] = ()


class Model(_Record):
    """A build: elements and instances, plus the components the instances place."""

    format: Literal["bricky/1"] = FORMAT
    name: str = "model"
    elements: tuple[Element, ...] = ()
    instances: tuple[Instance, ...] = ()
    components: dict[str, Component] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        _check_scope("the model", self.elements, self.instances, self.components)
        for name, component in self.components.items():
            _check_scope(
                f"component {name!r}",
                component.elements,
                component.instances,
                self.components,
            )
        _check_acyclic(self.components)
        return self

    def element_count(self) -> int:
        """Count the elements the model expands to, with every instance unfolded."""

        @cache
        def size(name: str) -> int:
            component = self.components[name]
            return len(component.elements) + sum(
                size(instance.component) for instance in component.instances
            )

        return len(self.elements) + sum(
            size(instance.component) for instance in self.instances
        )


def _check_scope(
    scope: str,
    elements: Sequence[Element],
    instances: Sequence[Instance],
    components: Mapping[str, Component],
) -> None:
    seen: set[str] = set()
    for item in (*elements, *instances):
        if item.id in seen:
            message = f"duplicate id {item.id!r} in {scope}"
            raise ValueError(message)
        seen.add(item.id)
    for instance in instances:
        if instance.component not in components:
            name = instance.component
            message = (
                f"instance {instance.id!r} in {scope} places unknown component {name!r}"
            )
            raise ValueError(message)


def _check_acyclic(components: Mapping[str, Component]) -> None:
    done: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in path:
            cycle = " -> ".join((*path[path.index(name) :], name))
            message = f"components place each other in a cycle: {cycle}"
            raise ValueError(message)
        if name in done:
            return
        for instance in components[name].instances:
            visit(instance.component, (*path, name))
        done.add(name)

    for name in components:
        visit(name, ())
