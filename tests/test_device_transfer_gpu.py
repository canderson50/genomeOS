"""Optional CUDA checks for bit-exact device transfer (design §7, §8; #276).

Skipped without CuPy and a working CUDA device. On a device they confirm that negative zero keeps
its sign bit through ``to_device_exact`` and that the unchanged scaled-arithmetic core then refuses
the noncanonical pairs it refuses on NumPy.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from genomeos.validation import count_scaled as cs
from genomeos.validation.device_transfer import to_device_exact

NEGATIVE_ZERO_BITS = 0x8000000000000000


def _cupy_device_available() -> bool:
    if importlib.util.find_spec("cupy") is None:
        return False
    import cupy as cp

    try:
        return cp.cuda.runtime.getDeviceCount() > 0
    except cp.cuda.runtime.CUDARuntimeError:
        return False


GPU_AVAILABLE = _cupy_device_available()
requires_gpu = pytest.mark.skipif(not GPU_AVAILABLE, reason="requires a working CUDA device")

NONCANONICAL = [
    (-0.0, 0.0, 0),
    (0.0, -0.0, 0),
    (-0.0, -0.0, 0),
    (0.0, 2.0**-121, 0),
    (0.25, 0.0, 0),
    (0.0, 0.0, 1),
]


def _bits(device) -> np.ndarray:
    return np.asarray(device.get()).view(np.uint64)


@requires_gpu
@pytest.mark.parametrize(
    "host",
    [
        np.asarray(-0.0),
        np.asarray(0.0),
        np.asarray([-0.0]),
        np.asarray([[-0.0, 0.5], [2.0**-1074, -np.inf]]),
        np.asarray([[-0.0, 1.0], [0.5, -0.0]]).T,
    ],
)
def test_cupy_transfer_preserves_shape_dtype_and_bits(host):
    import cupy as cp

    device = to_device_exact(host, array_module=cp)

    assert isinstance(device, cp.ndarray)
    assert device.shape == host.shape
    assert device.dtype == host.dtype
    np.testing.assert_array_equal(_bits(device).reshape(host.shape), host.view(np.uint64))


@requires_gpu
def test_cupy_zero_dimensional_negative_zero_keeps_its_sign_bit():
    import cupy as cp

    device = to_device_exact(np.asarray(-0.0), array_module=cp)

    assert device.shape == ()
    assert bool(cp.signbit(device))
    assert int(_bits(device.reshape(1))[0]) == NEGATIVE_ZERO_BITS


@requires_gpu
@pytest.mark.parametrize("row", NONCANONICAL)
def test_noncanonical_pairs_uploaded_exactly_fail_closed_on_cupy(row):
    import cupy as cp

    hi, lo, exponent = (np.asarray(row[0]), np.asarray(row[1]), np.asarray(row[2], dtype=np.int64))
    with pytest.raises(ValueError):
        cs.to_float64(cs.ScaledPair(hi, lo, exponent), array_module=np)

    bad = cs.ScaledPair(*(to_device_exact(field, array_module=cp) for field in (hi, lo, exponent)))
    one = cs.from_int64(cp.asarray([1], dtype=cp.int64).reshape(()), array_module=cp)
    for operation in (cs.add, cs.subtract, cs.multiply, cs.divide):
        with pytest.raises(ValueError):
            operation(bad, one, array_module=cp)
    with pytest.raises(ValueError):
        cs.to_float64(bad, array_module=cp)


@requires_gpu
def test_plain_asarray_zero_dimensional_negative_zero_behaviour_is_recorded(record_property):
    """Records, without asserting, what plain ``cp.asarray`` does to a 0-D negative zero.

    #276 observed positive zero under CuPy 14.2.0. The outcome is recorded rather than asserted so
    a CuPy fix does not turn this suite red; the exact-transfer tests above carry the guarantee.
    """
    import cupy as cp

    plain = cp.asarray(np.asarray(-0.0))
    sign_kept = bool(cp.signbit(plain))
    record_property("cupy_version", cp.__version__)
    record_property("plain_asarray_0d_negative_zero_sign_kept", sign_kept)
    print(f"cupy {cp.__version__}: plain asarray keeps 0-D negative-zero sign bit = {sign_kept}")
