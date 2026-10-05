"""In-memory time-series storage: validated writes and deterministic range queries."""
from __future__ import annotations

import math


def _validate_metric(metric: object) -> str:
    if not isinstance(metric, str):
        raise TypeError(f"metric name must be str, got {type(metric).__name__}")
    if not metric:
        raise ValueError("metric name must not be empty")
    return metric


def _validate_tags(tags: object) -> frozenset:
    if not isinstance(tags, dict):
        raise TypeError(f"tags must be a dict, got {type(tags).__name__}")
    for key, value in tags.items():
        if not isinstance(key, str):
            raise TypeError(f"tag key must be str, got {type(key).__name__}")
        if not key:
            raise ValueError("tag key must not be empty")
        if not isinstance(value, str):
            raise TypeError(f"tag value must be str, got {type(value).__name__}")
    return frozenset(tags.items())


def _validate_timestamp(timestamp: object, name: str = "timestamp") -> int:
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise TypeError(f"{name} must be an int (nanoseconds), got {type(timestamp).__name__}")
    return timestamp


def _validate_value(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"value must be int or float, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be finite (no NaN or infinities)")
    return value


class TimeSeriesStore:
    """Stores points per (metric, tag-set) series, keyed by nanosecond timestamp."""

    def __init__(self) -> None:
        self._series: dict[tuple[str, frozenset], dict[int, int | float]] = {}

    @staticmethod
    def _validate_point(metric, tags, timestamp, value):
        metric = _validate_metric(metric)
        tag_set = _validate_tags(tags)
        timestamp = _validate_timestamp(timestamp)
        value = _validate_value(value)
        return (metric, tag_set), timestamp, value

    def write(self, metric: str, tags: dict, timestamp: int, value) -> None:
        """Write a single point; a later write to the same series+timestamp overwrites."""
        key, timestamp, value = self._validate_point(metric, tags, timestamp, value)
        self._series.setdefault(key, {})[timestamp] = value

    def write_many(self, points) -> None:
        """Atomically write a batch of (metric, tags, timestamp, value) points.

        Every point is validated before any is applied, so one invalid point
        rejects the whole batch. Within the batch, later points overwrite
        earlier ones for the same series+timestamp.
        """
        if isinstance(points, (str, bytes)) or not hasattr(points, "__iter__"):
            raise TypeError("points must be an iterable of (metric, tags, timestamp, value)")
        validated = []
        for point in points:
            try:
                metric, tags, timestamp, value = point
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    "each point must be a 4-item iterable (metric, tags, timestamp, value)"
                ) from exc
            validated.append(self._validate_point(metric, tags, timestamp, value))
        for key, timestamp, value in validated:
            self._series.setdefault(key, {})[timestamp] = value

    def query(self, metric: str, tags: dict, start: int, end: int) -> list:
        """Return [(timestamp, value), ...] for one series over [start, end), sorted by time."""
        key = (_validate_metric(metric), _validate_tags(tags))
        start = _validate_timestamp(start, "start")
        end = _validate_timestamp(end, "end")
        if start > end:
            raise ValueError(f"start must not be greater than end ({start} > {end})")
        series = self._series.get(key)
        if series is None or start == end:
            return []
        return [(ts, series[ts]) for ts in sorted(series) if start <= ts < end]
