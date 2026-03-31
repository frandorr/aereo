"""Tests for the temporal component.

Verifies TimeRange creation, intersection, overlap detection, partitioning,
and datetime rounding utilities.
"""

from datetime import datetime, timedelta
import pytest
from returns.maybe import Nothing

from aer.temporal.core import TimeRange, round_to_next_t_minutes


def test_time_range_creation():
    start = datetime(2023, 1, 1, 10, 0)
    end = datetime(2023, 1, 1, 12, 0)
    tr = TimeRange(start=start, end=end)
    assert tr.start == start
    assert tr.end == end


def test_time_range_invalid_creation():
    start = datetime(2023, 1, 1, 12, 0)
    end = datetime(2023, 1, 1, 10, 0)
    with pytest.raises(ValueError, match="start \\(.*\\) must be before end \\(.*\\)"):
        TimeRange(start=start, end=end)

    # Same time shouldn't be allowed as per start_smaller_than_end
    with pytest.raises(ValueError):
        TimeRange(start=start, end=start)


def test_time_range_str_and_repr():
    start = datetime(2023, 1, 1, 10, 0)
    end = datetime(2023, 1, 1, 12, 0)
    tr = TimeRange(start=start, end=end)
    expected_str = f"{start} - {end}"
    assert str(tr) == expected_str
    assert repr(tr) == expected_str


def test_time_range_intersection():
    tr1 = TimeRange(start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 12, 0))
    tr2 = TimeRange(start=datetime(2023, 1, 1, 11, 0), end=datetime(2023, 1, 1, 13, 0))

    # Overlapping
    intersection1 = tr1.intersection(tr2)
    assert intersection1.value_or(None) == TimeRange(
        start=datetime(2023, 1, 1, 11, 0), end=datetime(2023, 1, 1, 12, 0)
    )

    # Non-overlapping
    tr3 = TimeRange(start=datetime(2023, 1, 1, 13, 0), end=datetime(2023, 1, 1, 14, 0))
    intersection2 = tr1.intersection(tr3)
    assert intersection2 == Nothing

    # Touching but not overlapping (start == end)
    tr4 = TimeRange(start=datetime(2023, 1, 1, 12, 0), end=datetime(2023, 1, 1, 13, 0))
    intersection3 = tr1.intersection(tr4)
    assert intersection3 == Nothing


def test_time_range_overlaps():
    tr1 = TimeRange(start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 12, 0))
    tr2 = TimeRange(start=datetime(2023, 1, 1, 11, 0), end=datetime(2023, 1, 1, 13, 0))
    tr3 = TimeRange(start=datetime(2023, 1, 1, 13, 0), end=datetime(2023, 1, 1, 14, 0))

    assert tr1.overlaps(tr2) is True
    assert tr1.overlaps(tr3) is False


def test_time_range_partition():
    tr1 = TimeRange(start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 12, 0))

    # Equal partitions
    partitions = tr1.partition(timedelta(hours=1))
    assert len(partitions) == 2
    assert partitions[0] == TimeRange(
        start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 11, 0)
    )
    assert partitions[1] == TimeRange(
        start=datetime(2023, 1, 1, 11, 0), end=datetime(2023, 1, 1, 12, 0)
    )

    # Non-equal partitions (last step is truncated)
    partitions2 = tr1.partition(timedelta(minutes=75))
    assert len(partitions2) == 2
    assert partitions2[0] == TimeRange(
        start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 11, 15)
    )
    assert partitions2[1] == TimeRange(
        start=datetime(2023, 1, 1, 11, 15), end=datetime(2023, 1, 1, 12, 0)
    )

    # Step larger than range
    partitions3 = tr1.partition(timedelta(hours=3))
    assert len(partitions3) == 1
    assert partitions3[0] == tr1


def test_time_range_partition_invalid_step():
    tr1 = TimeRange(start=datetime(2023, 1, 1, 10, 0), end=datetime(2023, 1, 1, 12, 0))
    with pytest.raises(ValueError, match="step \\(.*\\) must be positive"):
        tr1.partition(timedelta(0))
    with pytest.raises(ValueError, match="step \\(.*\\) must be positive"):
        tr1.partition(timedelta(hours=-1))


def test_round_to_next_t_minutes():
    dt = datetime(2023, 1, 1, 10, 14)
    rounded = round_to_next_t_minutes(dt, 15)
    assert rounded == datetime(2023, 1, 1, 10, 15)

    dt2 = datetime(2023, 1, 1, 10, 15)
    rounded2 = round_to_next_t_minutes(dt2, 15)
    assert rounded2 == datetime(2023, 1, 1, 10, 30)

    dt3 = datetime(2023, 1, 1, 10, 0, 30)
    rounded3 = round_to_next_t_minutes(dt3, 15)
    assert rounded3 == datetime(2023, 1, 1, 10, 15, 30)
