from pathlib import Path
from typing import Any

from oas_tools.utils import open_oas

ASSET_PATH = Path(__file__).parent / "assets"


def asset_filename(filename: str) -> str:
    return str(ASSET_PATH / filename)


def open_test_oas(filename: str) -> Any:
    return open_oas(asset_filename(filename))


def to_ascii(s: str) -> str:
    """
    Return string with '.' in place of all non-ASCII characters (other than newlines).

    This avoids differences in terminal output for non-ASCII characters like, table borders. The
    newline is passed through to let original look "almost" like the modified version.
    """
    return "".join(
        char if 31 < ord(char) < 127 or char == "\n" else "." for char in s
    ).rstrip()
