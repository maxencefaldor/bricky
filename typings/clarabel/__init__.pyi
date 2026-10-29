# Copyright 2026 Maxence Faldor
# Types for the parts of Clarabel that bricky uses, since Clarabel ships no stubs.

from collections.abc import Sequence
from enum import Enum

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csc_array

class SolverStatus(Enum):
    Unsolved = ...
    Solved = ...
    PrimalInfeasible = ...
    DualInfeasible = ...
    AlmostSolved = ...
    AlmostPrimalInfeasible = ...
    AlmostDualInfeasible = ...
    MaxIterations = ...
    MaxTime = ...
    NumericalError = ...
    InsufficientProgress = ...
    CallbackTerminated = ...

class ZeroConeT:
    def __init__(self, dim: int, /) -> None: ...

class NonnegativeConeT:
    def __init__(self, dim: int, /) -> None: ...

class DefaultSettings:
    verbose: bool
    iterative_refinement_max_iter: int
    iterative_refinement_reltol: float
    iterative_refinement_abstol: float

class DefaultSolution:
    x: list[float]
    z: list[float]
    s: list[float]
    status: SolverStatus
    iterations: int

class DefaultSolver:
    def __init__(
        self,
        P: csc_array,  # noqa: N803 - Clarabel's own name
        q: NDArray[np.float64],
        A: csc_array,  # noqa: N803 - Clarabel's own name
        b: NDArray[np.float64],
        cones: Sequence[ZeroConeT | NonnegativeConeT],
        settings: DefaultSettings,
        /,
    ) -> None: ...
    def solve(self) -> DefaultSolution: ...
