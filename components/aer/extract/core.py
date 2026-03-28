from typing import Any, Protocol

import pandera.pandas as pa
from pandera.typing import Series

from aer.search.core import SearchResultSchema, SearchResult
import attrs
from pathlib import Path
from enum import Enum


class ExtractionStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


@attrs.frozen
class ExtractionTask:
    """Task for extracting data from a search result to a standardized grid.

    This represents a single work unit for an extraction, containing the search results records,
    from which the target grid cells are derived.

    Attributes:
        search_results (list[SearchResult]): The search result records.
        output_dir (str): The directory to save the extracted data.
        auxiliary_data (dict[str, Any]): Auxiliary data for the extraction.
            Can be for example Geolocation data, or other data that is needed for the extraction.
            Depends on the user and the plugins how this is populated.
        extraction_params (dict[str, Any]): Parameters for the extraction.
        status (ExtractionStatus): The status of the extraction.
    """

    search_results: list[SearchResult]
    output_dir: Path
    auxiliary_data: dict[str, Any] = attrs.field(factory=dict)
    extraction_params: dict[str, Any] = attrs.field(factory=dict)
    status: ExtractionStatus = attrs.field(default=ExtractionStatus.PENDING)


class ExtractedResultSchema(SearchResultSchema):
    """Schema for extracted results, extending the search result metadata."""

    reprojected_path: Series[pa.String] = pa.Field(nullable=False)
    resolution: Series[float] = pa.Field(nullable=False)


class ExtractPlugin(Protocol):
    """Protocol for extract plugins.

    Design Decision:
        The `extract` method returns the input ExtractionTask directly, with its
        `status` field updated after extraction. This follows the command pattern:
        input task → output task (same object, mutated status).

        No separate ExtractionTaskResult is needed - the returned task carries
        the extraction status (PENDING → SUCCESS/FAILED) as part of its state.
    """

    def extract(
        self,
        task: ExtractionTask,
    ) -> ExtractionTask:
        """Extract data from a search result to a standardized grid.

        Args:
            task: The extraction task containing search result and output parameters.

        Returns:
            The input task with updated status field after extraction completes.
            Use task.status to check SUCCESS or FAILED.
        """
