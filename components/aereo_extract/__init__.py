"""AEREO remote extraction runtime (HTTP + AWS Lambda)."""

from aereo_extract.handlers import handle_lambda

__all__ = ["handle_lambda"]
