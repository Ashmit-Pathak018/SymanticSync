"""Process-wide coordination lock for tracked mutations and checkpoints.

This lock coordinates threads in one application process only. It does not
provide cross-process or distributed locking.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

MUTATION_CHECKPOINT_LOCK = threading.RLock()


def serialized_mutation(function: _F) -> _F:
    """Run a public tracked mutation under the shared checkpoint lock."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with MUTATION_CHECKPOINT_LOCK:
            return function(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
