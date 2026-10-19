"""Host-side checks for bit-exact device transfer (design §7, §8; #276)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from genomeos.validation.device_transfer import to_device_exact

NEGATIVE_ZERO_BITS = 0x8000000000000000


def _bits(array) -> np.ndarray:
    return np.asarray(array).view(np.uint64)


@pytest.mark.parametrize(
    "host",
    [
        np.asarray(-0.0),
        np.asarray(0.0),
        np.asarray([-0.0, 0.0, 0.5, -0.75]),
        np.asarray([[-0.0, 2.0**-1074], [np.inf, -np.inf]]),
        np.asarray([[-0.0, 1.0], [0.5, -0.0]]).T,
    ],
)
def test_numpy_namespace_round_trip_preserves_shape_dtype_and_bits(host):
    device = to_device_exact(host, array_module=np)

    assert device.shape == host.shape
    assert device.dtype == host.dtype
    np.testing.assert_array_equal(_bits(device), _bits(host))


def test_zero_dimensional_negative_zero_keeps_its_sign_bit():
    device = to_device_exact(np.asarray(-0.0), array_module=np)

    assert device.shape == ()
    assert int(_bits(device)) == NEGATIVE_ZERO_BITS


@pytest.mark.parametrize("dtype", [np.int64, np.uint64, np.bool_])
def test_non_float_dtypes_round_trip(dtype):
    host = np.asarray([0, 1, 1], dtype=dtype)

    device = to_device_exact(host, array_module=np)

    assert device.dtype == host.dtype
    assert device.tobytes() == host.tobytes()


def test_transfer_does_not_alias_or_mutate_the_host_array():
    host = np.asarray([-0.0, 0.5])
    before = host.copy()

    device = to_device_exact(host, array_module=np)
    device[1] = 0.25

    assert host.tobytes() == before.tobytes()


@pytest.mark.parametrize("value", [-0.0, [-0.0], (0.5,)])
def test_non_numpy_inputs_are_refused(value):
    with pytest.raises(TypeError, match="NumPy array"):
        to_device_exact(value, array_module=np)


def test_object_dtype_is_refused():
    with pytest.raises(TypeError, match="object"):
        to_device_exact(np.asarray([-0.0], dtype=object), array_module=np)


def test_a_namespace_that_drops_the_sign_bit_fails_closed():
    lossy = SimpleNamespace(asarray=lambda array: np.abs(np.asarray(array)))

    with pytest.raises(ValueError, match="bit pattern"):
        to_device_exact(np.asarray(-0.0), array_module=lossy)


def test_a_namespace_that_changes_dtype_fails_closed():
    widened = SimpleNamespace(asarray=lambda array: np.asarray(array, dtype=np.float32))

    with pytest.raises(ValueError, match="dtype or length"):
        to_device_exact(np.asarray([0.5]), array_module=widened)
