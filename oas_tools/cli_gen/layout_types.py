import dataclasses
from enum import Enum
from typing import Any
from typing import Optional


class LayoutField(str, Enum):
    NAME = "name"
    BUG_IDS = "bugIds"
    DESCRIPTION = "description"
    OP_ID = "operationId"
    OPERATIONS = "operations"
    SUB_ID = "subcommandId"
    SUMMARY_FIELDS = "summaryFields"

@dataclasses.dataclass
class CommandNode:
    command: str
    identifier: str
    description: str = ""
    bugs: list[str] = dataclasses.field(default_factory=list)
    summary_fields: list[str] = dataclasses.field(default_factory=list)
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)
    children: list["CommandNode"] = dataclasses.field(default_factory=list)

    def as_dict(self, sparse: bool = True) -> dict[str, Any]:
        """Convenience method to convert to dictionary"""
        def filter_empty_or_none(d: list[tuple[str, Any]]) -> dict[str, Any]:
            """Skips keys whose value is None, or an empty list/dict/set"""
            return {k: v for (k, v) in d if v is not None and v != [] and v != {}}

        return dataclasses.asdict(self, dict_factory=filter_empty_or_none if sparse else None)

    def subcommands(self, include_bugged: bool = False) -> list["CommandNode"]:
        """Return a list of CommandNodes that have children."""
        return [n for n in self.children if n.children and (include_bugged or not n.bugs)]

    def operations(self, include_bugged: bool = False) -> list["CommandNode"]:
        """Return a list of CommandNodes without any children."""
        return [n for n in self.children if not n.children and (include_bugged or not n.bugs)]

    def find(self, *args) -> Optional["CommandNode"]:
        """Search for the provided commands"""
        for child in self.children:
            if child.command == args[0]:
                if len(args) == 1:
                    return child
                return child.find(*args[1:])

        return None
