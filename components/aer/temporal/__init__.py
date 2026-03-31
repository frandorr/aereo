"""
Temporal component for working with time ranges, including intersection,
overlap detection, partitioning, and rounding to time boundaries.
"""

from aer.temporal.core import TimeRange, ceil_to_next_t_minutes, round_to_next_t_minutes

__all__ = ["TimeRange", "ceil_to_next_t_minutes", "round_to_next_t_minutes"]
