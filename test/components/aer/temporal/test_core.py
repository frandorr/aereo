from datetime import datetime
import pytest
from returns.maybe import Nothing

from aer.temporal.core import TimeRange


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
