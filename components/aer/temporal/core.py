import attrs
from datetime import datetime, timedelta
from returns import maybe


@attrs.frozen
class TimeRange:
    start: datetime
    end: datetime

    def __str__(self) -> str:
        return f"{self.start} - {self.end}"

    def __repr__(self) -> str:
        return self.__str__()

    def intersection(self, other: "TimeRange") -> maybe.Maybe["TimeRange"]:
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
            return maybe.Nothing
        return maybe.Some(TimeRange(start=start, end=end))

    def overlaps(self, other: "TimeRange") -> bool:
        return self.intersection(other) != maybe.Nothing

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


def round_to_next_t_minutes(dt: datetime, t: int) -> datetime:
    """
    Rounds the given datetime to the next multiple of t minutes.

    Args:
        dt: The datetime to round.
        t: The number of minutes to round to.

    Returns:
        The rounded datetime.
    """
    return dt + timedelta(minutes=t - dt.minute % t)
