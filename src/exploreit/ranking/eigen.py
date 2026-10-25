"""Ranking by the eigenvector of the largest eigenvalue, found with the power method.

Prestige that no longer changes satisfies lambda * p = A^T p: p is an eigenvector of
A^T (equivalently a left eigenvector of the adjacency matrix A). For a matrix with no
negative entries the largest eigenvalue has an eigenvector with no negative entries
(Perron-Frobenius theorem), so it can be read directly as a ranking.

The power method multiplies a starting vector by the matrix again and again; the part
along the largest eigenvalue grows fastest and soon dominates. Graphs whose pages split
into alternating groups have a second eigenvalue of the same size with the opposite
sign, which makes the plain method swap forever. Shifting the matrix, A^T + s * I,
keeps the eigenvectors but moves every eigenvalue by s, so the largest one is unique.
"""

from dataclasses import dataclass

import numpy as np

from exploreit.ranking.matrix import Matrix


@dataclass(frozen=True)
class EigenResult:
    value: float  # the largest eigenvalue of A^T, which A shares
    vector: np.ndarray  # its eigenvector, non-negative and scaled to sum to 1
    iterations: int
    converged: bool


def leading_eigenvector(
    matrix: Matrix, *, shift: float = 1.0, tolerance: float = 1e-10, max_iterations: int = 10_000
) -> EigenResult:
    """Power method on A^T + shift * I."""
    size = matrix.shape[0]
    if size == 0:
        return EigenResult(0.0, np.empty(0), 0, True)
    transposed = matrix.T
    vector = np.full(size, 1.0 / size)
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):  # noqa: B007 - reported below
        following = transposed @ vector + shift * vector
        following /= following.sum()
        change = float(np.abs(following - vector).max())
        vector = following
        if change <= tolerance:
            converged = True
            break
    # Rayleigh quotient: the eigenvalue that best fits the vector found.
    value = float(vector @ (transposed @ vector) / (vector @ vector))
    return EigenResult(value, vector, iterations, converged)


def numpy_eigenvector(matrix: Matrix) -> EigenResult:
    """The same eigenvector from numpy's general eigenvalue solver, as a cross-check.

    This plays the role of the external calculator suggested by the task.
    """
    if matrix.shape[0] == 0:
        return EigenResult(0.0, np.empty(0), 0, True)
    values, vectors = np.linalg.eig(matrix.T)
    best = int(np.argmax(values.real))
    vector = np.abs(vectors[:, best].real)
    return EigenResult(float(values[best].real), vector / vector.sum(), 0, True)
