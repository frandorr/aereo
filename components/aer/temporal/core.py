import attrs
from datetime import datetime
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
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start >= end:
            return maybe.Nothing
        return maybe.Some(TimeRange(start=start, end=end))

    def overlaps(self, other: "TimeRange") -> bool:
        return self.intersection(other) != maybe.Nothing

    def __attrs_post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"start ({self.start}) must be before end ({self.end})")
