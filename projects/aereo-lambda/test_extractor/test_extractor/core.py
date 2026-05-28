"""Minimal test extractor for AEREO lambda integration testing."""

from __future__ import annotations

from typing import Any

from aereo.interfaces import Extractor, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class TestExtractor(Extractor, plugin_abstract=False):
    """A dummy extractor that returns empty artifacts for testing."""

    supported_collections = ["GOES"]

    def extract(
        self,
        extraction_task: ExtractionTask,
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Return empty artifacts GeoDataFrame."""
        return ArtifactSchema.empty_geodataframe()
