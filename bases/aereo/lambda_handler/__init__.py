"""Public API entry-point for the Aereo Lambda handler.

This module re-exports the handler function that AWS Lambda invokes:

- :func:`handler`: The main Lambda handler entrypoint.
"""

from aereo.lambda_handler.core import handler

__all__ = ["handler"]
