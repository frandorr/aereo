"""Standalone task preparation (replaces the legacy Extractor plugin).

Exposes :func:`prepare_for_extraction` as a pure function so the client can
build extraction tasks without registering a plugin.
"""

from aereo.task_builder.core import prepare_for_extraction

__all__ = ["prepare_for_extraction"]
