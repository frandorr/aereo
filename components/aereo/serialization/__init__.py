"""Task serialization for cross-network transport.

Persists :class:`ExtractionTask` as a pair of files (GeoParquet + JSON) so it
can be shipped to remote workers (e.g. AWS Lambda).
"""

from aereo.serialization.core import TaskSerializer

__all__ = ["TaskSerializer"]
