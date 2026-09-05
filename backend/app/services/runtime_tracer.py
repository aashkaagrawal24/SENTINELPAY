"""Per-layer runtime tracer for E2E flow analysis.

Every layer emits a timing entry; the full trace is returned as a serializable
list so it can be stored in the audit ledger or returned via the E2E trace API.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSpan:
    layer: str
    started_ms: float
    ended_ms: float = 0
    duration_ms: float = 0
    status: str = "OK"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeTrace:
    trace_id: str
    spans: list[TraceSpan] = field(default_factory=list)
    _origin: float = field(default_factory=lambda: time.perf_counter() * 1000, repr=False)

    @contextmanager
    def span(self, layer: str, **detail: Any) -> Generator[TraceSpan, None, None]:
        started = time.perf_counter() * 1000
        entry = TraceSpan(
            layer=layer,
            started_ms=round(started - self._origin, 3),
            detail=detail,
        )
        try:
            yield entry
        except Exception as exc:
            entry.status = type(exc).__name__
            raise
        finally:
            ended = time.perf_counter() * 1000
            entry.ended_ms = round(ended - self._origin, 3)
            entry.duration_ms = round(ended - started, 3)
            self.spans.append(entry)

    @property
    def total_ms(self) -> float:
        return round(sum(item.duration_ms for item in self.spans), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "total_ms": self.total_ms,
            "span_count": len(self.spans),
            "spans": [
                {
                    "layer": item.layer,
                    "started_ms": item.started_ms,
                    "ended_ms": item.ended_ms,
                    "duration_ms": item.duration_ms,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in self.spans
            ],
        }
