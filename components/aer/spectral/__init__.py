"""
spectral defines the canonical, instrument-agnostic data model for spectral measurements used across the system. It provides the structural types, typestate markers, and taxonomy primitives required to represent Earth observation bands in a consistent and type-safe way.

This component contains no IO, no satellite-specific logic, and no transformation algorithms. It encodes structure and invariants only.
"""

from aer.spectral.core import Band, TOA, Visible

__all__ = ["Band", "TOA", "Visible"]
