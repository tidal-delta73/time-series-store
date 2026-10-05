"""In-memory time-series store: single-point writes and deterministic range queries."""
from __future__ import annotations

import math
from typing import Iterable, Tuple

# A series is identified by its metric name plus its tag set; tag order is
# irrelevant, so the key uses a frozenset of (key, value) pairs.
_SeriesKey = Tuple[str, frozenset]


def _validate_metric(metric: str) -> str:
    if not isinstance(metric, str):
        raise TypeError(f"metric name must be str, got {type(metric).__name__}")
    if not metric:
        raise ValueError("metric name must not be empty")
    return metric


def _validate_tags(tags: dict) -> frozenset:
    if not isinstance(tags, dict):
        raise TypeError(f"tags must be a dict, got {type(tags).__name__}")
    for key, value in tags.items():
        if not isinstance(key, str):
            raise TypeError(f"tag key must be str, got {type(key).__name__}")
        if not key:
            raise ValueError("tag key must not be empty")
        if not isinstance(value, str):
            raise TypeError(f"tag value must be str, got {type(value).__name__}")
    # Freeze a copy so later caller-side mutation of the dict cannot affect identity.
    return frozenset(tags.items())


def _validate_timestamp(timestamp: int) -> int:
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise TypeError(f"timestamp must be int, got {type(timestamp).__name__}")
    return timestamp


def _validate_value(value) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"value must be int or float, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be finite (no NaN or infinity)")
    return value


class TimeSeriesStore:
    """Stores (timestamp, value) points per (metric, tag-set) series."""

    def __init__(self) -> None:
        self._series: dict[_SeriesKey, dict[int, int | float]] = {}

    def _validate_point(self, metric, tags, timestamp, value):
        return (
            (_validate_metric(metric), _validate_tags(tags)),
            _validate_timestamp(timestamp),
            _validate_value(value),
        )

    def write(self, metric: str, tags: dict, timestamp: int, value) -> None:
        """Write one point; re-writing an existing timestamp overwrites it."""
        key, timestamp, value = self._validate_point(metric, tags, timestamp, value)
        self._series.setdefault(key, {})[timestamp] = value

    def write_many(self, points: Iterable[tuple]) -> None:
        """Atomically write a batch of (metric, tags, timestamp, value) points.

        Every point is validated before any is applied, so an invalid point
        leaves the store unchanged. Within the batch, later points overwrite
        earlier ones at the same series/timestamp.
        """
        validated = [self._validate_point(m, t, ts, v) for m, t, ts, v in points]
        for key, timestamp, value in validated:
            self._series.setdefault(key, {})[timestamp] = value

    def query(self, metric: str, tags: dict, start: int, end: int) -> list:
        """Return (timestamp, value) pairs in [start, end), ascending by timestamp."""
        key = (_validate_metric(metric), _validate_tags(tags))
        start = _validate_timestamp(start)
        end = _validate_timestamp(end)
        if start > end:
            raise ValueError(f"start ({start}) must not be greater than end ({end})")
        series = self._series.get(key)
        if not series:
            return []
        return [(ts, series[ts]) for ts in sorted(series) if start <= ts < end]
