from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


def _opik_enabled() -> bool:
    # Opik can also run via OTEL env vars, but for hackathon friendliness we
    # enable spans if the SDK is installed and the user set an API key.
    return bool(os.getenv("OPIK_API_KEY") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


@contextmanager
def opik_trace(
    name: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    """
    Create a trace for a top-level AI function.

    If Opik isn't configured/installed, this becomes a no-op.
    """
    if not _opik_enabled():
        yield
        return

    try:
        from opik.context_manager import start_as_current_trace  # type: ignore
        from opik.context_manager import update_current_trace  # type: ignore
    except Exception:
        yield
        return

    with start_as_current_trace(name=name):
        if metadata:
            try:
                update_current_trace(metadata=metadata)
            except Exception:
                pass
        yield


@contextmanager
def opik_span(
    name: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    """
    Create a span under the current trace.

    If Opik isn't configured/installed, this becomes a no-op.
    """
    if not _opik_enabled():
        yield
        return

    try:
        from opik.context_manager import start_as_current_span  # type: ignore
        from opik.context_manager import update_current_span  # type: ignore
    except Exception:
        yield
        return

    with start_as_current_span(name=name):
        if metadata:
            try:
                update_current_span(metadata=metadata)
            except Exception:
                pass
        yield

