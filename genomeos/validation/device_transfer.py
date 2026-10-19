"""Bit-exact host-to-device array transfer for offline numerical qualification (design §7, §8; #276).

CuPy 14.2.0 ``asarray`` transfers a 0-D float64 negative zero as positive zero, so a harness that
uploads retained NumPy evidence with plain ``asarray`` can hand the scaled-arithmetic core an input
that differs from the one recorded. The core then correctly accepts the altered value and an
expected refusal never fires. This module uploads every array as a one-dimensional buffer, which
preserves the bit pattern, reads that buffer back and compares bytes before restoring the original
shape on the device. A transfer that changes any byte, the dtype, or the shape is an error, never a
silently accepted substitute.

The array namespace is caller-supplied, as in ``count_scaled``; CuPy is never imported here.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _host_copy(device: Any) -> np.ndarray:
    get = getattr(device, "get", None)
    return np.asarray(get() if callable(get) else device)


def to_device_exact(host: np.ndarray, *, array_module: Any) -> Any:
    """Return ``host`` on ``array_module``'s device with identical shape, dtype and bytes.

    Accepts only NumPy arrays with a fixed-size, non-object dtype. The uploaded one-dimensional
    buffer is read back and compared byte for byte before the device reshape, which changes only
    metadata. Raises TypeError for an unsupported input and ValueError when the transfer does not
    reproduce the host bytes, dtype, or shape.
    """
    if not isinstance(host, np.ndarray):
        raise TypeError("Bit-exact transfer requires a NumPy array")
    if host.dtype.hasobject:
        raise TypeError("Bit-exact transfer refuses object dtypes")
    flat = np.array(host, copy=True, order="C").reshape(-1)
    uploaded = array_module.asarray(flat)
    returned = _host_copy(uploaded)
    if returned.dtype != host.dtype or returned.shape != flat.shape:
        raise ValueError("Device transfer changed the array dtype or length")
    if returned.tobytes() != flat.tobytes():
        raise ValueError("Device transfer did not preserve the host bit pattern")
    device = uploaded.reshape(host.shape)
    if device.shape != host.shape or device.dtype != host.dtype:
        raise ValueError("Device reshape did not restore the host shape and dtype")
    return device
