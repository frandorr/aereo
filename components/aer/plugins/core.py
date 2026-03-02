import importlib.metadata
from typing import Iterable
from structlog import get_logger

logger = get_logger()


def load_entrypoint_group(group: str) -> None:
    """
    Load all entry points for a specific plugin group.

    Each entry point must resolve to a callable or object.
    Import side-effects are allowed but discouraged.
    """
    try:
        entry_points = importlib.metadata.entry_points(group=group)
    except Exception as exc:
        logger.warning("Failed to read entry points", group=group, error=str(exc))
        return

    for entry in entry_points:
        try:
            entry.load()
        except Exception as exc:
            logger.error(
                "Plugin failed to load",
                group=group,
                plugin=entry.name,
                error=str(exc),
            )


def load_multiple_groups(groups: Iterable[str]) -> None:
    """Load all entry points for multiple plugin groups."""
    for group in groups:
        load_entrypoint_group(group)
