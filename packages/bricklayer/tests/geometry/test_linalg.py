import math

import numpy as np
import pytest

from bricklayer import Mat3, Vec3
from bricklayer.geometry.linalg import (
    EPSILON,
    is_aligned,
    is_opposing,
    is_orthogonal,
    is_unit,
    rotation_between,
    vec_max,
    vec_min,
)


class TestVec3:
    def test_componentwise_arithmetic(self):
        a, b = Vec3(1, 2, 3), Vec3(10, 20, 30)
        assert a + b == Vec3(11, 22, 33)
        assert b - a == Vec3(9, 18, 27)
        assert -a == Vec3(-1, -2, -3)

    def test_scalar_multiplication_and_division(self):
        v = Vec3(1, 2, 3)
        assert v * 2 == Vec3(2, 4, 6)
        assert 2 * v == Vec3(2, 4, 6)
        assert v * 0.5 == Vec3(0.5, 1, 1.5)
        assert Vec3(2.0, 4.0, 6.0) / 2 == Vec3(1.0, 2.0, 3.0)

    def test_tuple_compatibility(self):
        v = Vec3(1, 2, 3)
        x, y, z = v
        assert (x, y, z) == (1, 2, 3)
        assert (v[0], v[1], v[2]) == (1, 2, 3)
        assert v[-1] == 3
        assert len(v) == 3
        assert tuple(v) == (1, 2, 3)

    def test_usable_as_a_set_and_dict_key(self):
        assert len({Vec3(1, 2, 3), Vec3(1, 2, 3), Vec3(0, 0, 0)}) == 2

    def test_repr_is_bare(self):
        # Integral components render without a trailing ``.0``; fractional ones
        # print as their float value.
        assert repr(Vec3(1, 2, 3)) == "Vec3(1, 2, 3)"
        assert repr(Vec3(1, 2, 0.5)) == "Vec3(1, 2, 0.5)"


class TestVecBounds:
    def test_vec_min_and_max(self):
        vecs = [Vec3(1, 2, 3), Vec3(0, 5, 1), Vec3(4, 1, 2)]
        assert vec_min(vecs) == Vec3(0, 1, 1)
        assert vec_max(vecs) == Vec3(4, 5, 3)

    def test_vec_min_and_max_raise_on_empty(self):
        with pytest.raises(ValueError):
            vec_min([])
        with pytest.raises(ValueError):
            vec_max([])


class TestDotProductChecks:
    def test_is_unit_accepts_unit_vectors_within_tolerance(self):
        assert is_unit(Vec3(0, 0, 1))
        assert is_unit(Vec3(0.6, 0.0, 0.8))
        assert is_unit(Vec3(1 + EPSILON / 4, 0, 0))

    def test_is_unit_rejects_non_unit_vectors(self):
        assert not is_unit(Vec3(0, 0, 2))
        assert not is_unit(Vec3(0, 0, 0))

    def test_is_orthogonal_accepts_perpendicular_vectors(self):
        assert is_orthogonal(Vec3(1, 0, 0), Vec3(0, 1, 0))
        assert is_orthogonal(Vec3(0, 0, 1), Vec3(0, 0, 0))

    def test_is_orthogonal_rejects_non_perpendicular_vectors(self):
        assert not is_orthogonal(Vec3(1, 0, 0), Vec3(1, 0, 0))
        assert not is_orthogonal(Vec3(1, 0, 0), Vec3(1, 1, 0))

    def test_is_opposing_accepts_antiparallel_unit_vectors(self):
        assert is_opposing(Vec3(0, 0, 1), Vec3(0, 0, -1))
        assert is_opposing(Vec3(0, 0, 1), Vec3(0, EPSILON / 4, -1))

    def test_is_opposing_rejects_aligned_or_orthogonal_vectors(self):
        assert not is_opposing(Vec3(0, 0, 1), Vec3(0, 0, 1))
        assert not is_opposing(Vec3(1, 0, 0), Vec3(0, 1, 0))

    def test_is_aligned_accepts_parallel_unit_vectors(self):
        assert is_aligned(Vec3(0, 0, 1), Vec3(0, 0, 1))
        assert is_aligned(Vec3(0, 0, 1), Vec3(0, EPSILON / 4, 1))

    def test_is_aligned_rejects_opposing_or_orthogonal_vectors(self):
        assert not is_aligned(Vec3(0, 0, 1), Vec3(0, 0, -1))
        assert not is_aligned(Vec3(1, 0, 0), Vec3(0, 1, 0))


class TestMat3:
    # A 90-degree turn about the vertical axis: (x, y, z) -> (-y, x, z).
    _A = Mat3(((1, 2, 3), (4, 5, 6), (7, 8, 9)))
    _ROT_90 = Mat3(((0, -1, 0), (1, 0, 0), (0, 0, 1)))

    def test_rejects_non_3x3_arrays(self):
        with pytest.raises(ValueError, match="3x3"):
            Mat3.from_array(np.array(((1, 2), (3, 4))))
        with pytest.raises(ValueError, match="3x3"):
            Mat3.from_array(np.array(((1, 2, 3), (4, 5, 6))))

    def test_item_accessor(self):
        assert self._A[0, 0] == 1
        assert self._A[0, 1] == 2
        assert self._A[0, 2] == 3
        assert self._A[1, 0] == 4
        assert self._A[1, 1] == 5
        assert self._A[1, 2] == 6
        assert self._A[2, 0] == 7
        assert self._A[2, 1] == 8
        assert self._A[2, 2] == 9

    def test_identity_leaves_a_matrix_and_a_vector_unchanged(self):
        assert Mat3.IDENTITY @ self._A == self._A
        assert Mat3.IDENTITY @ Vec3(2, 3, 5) == Vec3(2, 3, 5)

    def test_matrix_times_vector(self):
        # The 90-degree turn sends (2, 3, 5) -> (-3, 2, 5).
        assert self._ROT_90 @ Vec3(2, 3, 5) == Vec3(-3, 2, 5)

    def test_matrix_times_matrix(self):
        # A shear times another shear.
        a = Mat3(((1, 2, 0), (0, 1, 0), (0, 0, 1)))
        b = Mat3(((1, 0, 0), (3, 1, 0), (0, 0, 1)))
        assert a @ b == Mat3(((7, 2, 0), (3, 1, 0), (0, 0, 1)))

    def test_composes_two_rotations(self):
        # Two quarter turns compose into a half turn: (x, y, z) -> (-x, -y, z).
        half_turn = Mat3(((-1, 0, 0), (0, -1, 0), (0, 0, 1)))
        assert self._ROT_90 @ self._ROT_90 == half_turn

    def test_is_immutable(self):
        with pytest.raises(ValueError):
            self._A.array[0, 0] = 10


class TestRotationBetween:
    @pytest.mark.parametrize("gap", [0.0, 1e-16, 1e-12, 1e-9, 1e-7, 1e-6, 2e-6, 1e-3])
    def test_takes_near_antipodal_vectors_onto_each_other(self, gap):
        a = Vec3(0.0, 0.0, 1.0)
        angle = math.pi - gap
        b = Vec3(math.sin(angle), 0, math.cos(angle))
        r = rotation_between(a, b)
        assert (r @ a - b).norm() < 1e-8
        assert np.allclose((r @ r.transpose).array, np.eye(3), atol=1e-9)

    def test_takes_a_vector_onto_itself_unchanged(self):
        a = Vec3(0, 0.6, 0.8)
        assert np.allclose(rotation_between(a, a).array, np.eye(3))
