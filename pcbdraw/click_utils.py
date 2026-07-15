"""Shared Click command helpers."""

from functools import wraps
from typing import Any

import click

from .kicad_cli import KiCadCliError


def report_kicad_cli_errors(function: Any) -> Any:
    """Present backend failures as concise Click usage errors."""
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except KiCadCliError as error:
            raise click.ClickException(str(error)) from error
    return wrapped
