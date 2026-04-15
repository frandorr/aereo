"""
AER plugin registry. It acts as the central nervous system of aer, dynamically discovering plugins installed in the environment, validating them against interfaces contract, and routing user requests to the correct implementations.
"""

from aer.registry.core import AerRegistry

__all__ = ["AerRegistry"]
