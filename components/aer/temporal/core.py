"""Core temporal utilities for time range operations.

Provides TimeRange for representing time periods with intersection,
overlap detection, and partitioning, plus ceil_to_next_t_minutes()
for rounding datetimes to time boundaries.
"""

from typing import Optional
import attrs
from datetime import datetime, timedelta


@attrs.frozen
class TimeRange:
    """A representation of a continuous period of time.

    Attributes:
        start (datetime): The starting datetime of the period.
        end (datetime): The ending datetime of the period.
    """

    start: datetime
    end: datetime

    def __str__(self) -> str:
        """Get the string representation.

        Returns:
            str: Formatted period string 'start - end'.
        """
        return f"{self.start} - {self.end}"

    def __repr__(self) -> str:
        """Get the formal string representation.

        Returns:
            str: Formatted period string 'start - end'.
        """
        return self.__str__()

    def intersection(self, other: "TimeRange") -> Optional["TimeRange"]:
        """
        Returns the intersection of this time range and another time range.

        Args:
            other: The other time range to find the intersection of.

        Returns:
            The intersection of this time range and the other time range.
        """
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start >= end:
            return None
        return TimeRange(start=start, end=end)

    def overlaps(self, other: "TimeRange") -> bool:
        """Check if this time range overlaps with another time range.

        Args:
            other (TimeRange): The other time range to check.

        Returns:
            bool: True if there is an overlapping period, False otherwise.
        """
        return self.intersection(other) is not None

    def partition(self, step: timedelta) -> list["TimeRange"]:
        """
        Partitions the time range into a list of time ranges of the given step size .

        Args:
            step: The step size to partition the time range into.

        Returns:
            A list of time ranges of the given step size.
        """
        # check timedelta is positive
        if step <= timedelta(0):
            raise ValueError(f"step ({step}) must be positive")
        ranges = []
        current = self.start
        while current < self.end:
            next_step = min(current + step, self.end)
            ranges.append(TimeRange(start=current, end=next_step))
            current = next_step
        return ranges

    def __attrs_post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"start ({self.start}) must be before end ({self.end})")


def ceil_to_next_t_minutes(dt: datetime, t: int) -> datetime:
    """
    Rounds the given datetime up to the next multiple of t minutes.

    Always advances to the next boundary, even if `dt` is already aligned.

    Args:
        dt: The datetime to round.
        t: The number of minutes to round to.

    Returns:
        The rounded datetime.
    """
    return dt + timedelta(minutes=t - dt.minute % t)


# Keep old name as alias for backwards compatibility
round_to_next_t_minutes = ceil_to_next_t_minutes
