"""Common extensions to Typer for local CLI use."""

import typer
from rich import print
from typing_extensions import Annotated

# Common argument definition
OasFilenameArgument = Annotated[str, typer.Argument(show_default=False, help="OpenAPI specification file")]


def error_out(message: str, exit_code: int = 1) -> None:
    """Print provided error message (with red ERROR prefix) and exit."""
    print(f"[red]ERROR:[/red] {message}")
    raise typer.Exit(exit_code)


