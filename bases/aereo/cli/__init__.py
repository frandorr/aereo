"""Public API entry-point for the Aereo CLI.

This module re-exports the Typer application that consumers and
entry-point wrappers interact with:

- :attr:`app`: The main Typer CLI application.
"""

from aereo.cli.main import main

__all__ = ["main"]
