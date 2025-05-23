import dataclasses
from enum import Enum
from typing import Optional

from rich.table import Table

INDENT = "  "


class TreeDisplay(str, Enum):
    HELP = "help"
    FUNCTION = "function"
    OPERATION = "operation"
    PATH = "path"
    ALL = "all"


class TreeField(str, Enum):
    OPERATIONS = "operations"
    DESCRIPTION = "description"

    NAME = "name"
    OP_ID = "operationId"
    METHOD = "method"
    HELP = "help"
    PATH = "path"
    SUB_CMD = "subcommandId"
    FUNC = "function"
    MODULE = "module"


@dataclasses.dataclass
class TreeNode:
    name: str
    help: Optional[str] = None
    operation: Optional[str] = None
    function: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    children: list["TreeNode"] = dataclasses.field(default_factory=list)

    def get(self, display: TreeDisplay) -> str:
        if display == TreeDisplay.HELP:
            return self.help or ''
        if display == TreeDisplay.FUNCTION:
            return self.function or ''
        if display == TreeDisplay.OPERATION:
            return self.operation or ''
        if display == TreeDisplay.PATH:
            return f"{self.method.upper():6} {self.path}" if self.path else ''
        return None


def create_node_table(node: TreeNode) -> Table:
    """Creates the "inner" table for an individual node."""
    table = Table(
        highlight=True,
        show_header=False,
        show_lines=False,
        show_edge=False,
        row_styles=None,
        expand=False,
        caption_justify="left",
        border_style=None,
        leading=0,
        pad_edge=False,
        padding=(0, 1),
        box=None,
    )
    table.add_column("Property", justify="left", no_wrap=True, overflow="ignore")
    table.add_column("Value", justify="left", no_wrap=True, overflow="ignore")
    for display in [TreeDisplay.HELP, TreeDisplay.OPERATION, TreeDisplay.PATH, TreeDisplay.FUNCTION]:
        value = node.get(display)
        if value:
            table.add_row(display.value, value)

    return table


def add_node_to_table(table: Table, node: TreeNode, display: TreeDisplay, depth: int, max_depth: int) -> None:
    indent = INDENT * depth
    if display != TreeDisplay.ALL:
        content = node.get(display)
    else:
        content = create_node_table(node)

    table.add_row(indent + node.name, content)
    if max_depth > depth:
        for child in node.children:
            add_node_to_table(table, child, display, depth + 1, max_depth)


def create_tree_table(node: TreeNode, display: TreeDisplay, max_depth: int) -> Table:
    table = Table(
        highlight=False,
        show_header=False,
        expand=True,
        box=None,
        show_lines=False,
        leading=0,
        border_style=None,
        row_styles=None,
        pad_edge=False,
        padding=(0, 1),
    )
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column(display.value.title())
    for child in node.children:
        add_node_to_table(table, child, display, 0, max_depth)

    return table
