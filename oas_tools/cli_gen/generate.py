import os
from pathlib import Path
from typing import Any

from oas_tools.cli_gen._logging import logger
from oas_tools.cli_gen._tree import TreeField
from oas_tools.cli_gen._tree import TreeNode
from oas_tools.cli_gen.constants import GENERATOR_LOG_CLASS
from oas_tools.cli_gen.generator import COPYRIGHT
from oas_tools.cli_gen.generator import Generator
from oas_tools.cli_gen.layout_types import LayoutNode
from oas_tools.cli_gen.utils import to_snake_case
from oas_tools.types import OasField
from oas_tools.utils import map_operations

# Maps the source to destination (currently all the same).
INFRASTRUCTURE_FILES = {
    "_arguments.py": "_arguments.py",
    "_display.py": "_display.py",
    "_exceptions.py": "_exceptions.py",
    "_logging.py": "_logging.py",
    "_requests.py": "_requests.py",
}

TEST_FILES = {
    "helpers.py": "helpers.py",
    "test_display.py": "test_display.py",
    "test_exceptions.py": "test_exceptions.py",
    "test_logging.py": "test_logging.py",
    "test_requests.py": "test_requests.py",
}

logger = logger(GENERATOR_LOG_CLASS)


def generate_node(generator: Generator, node: LayoutNode, directory: str) -> None:
    """Creates a file/module for the current node, and recursively goes through sub-commands."""
    module_name = to_snake_case(node.identifier)
    logger.info(f"Generating {module_name} module")
    text = generator.shebang()
    text += generator.copyright()
    text += generator.standard_imports()
    text += generator.subcommand_imports(node.subcommands())
    text += generator.app_definition(node)
    for command in node.operations():
        text += generator.function_definition(command)
    text += generator.main()

    filename = os.path.join(directory, module_name + ".py")
    with open(filename, "w") as fp:
        fp.write(text)
    os.chmod(filename, 0o755)

    # recursively do the same for sub-commands
    for command in node.subcommands():
        generate_node(generator, command, directory)


def generate_tree_node(generator: Generator, node: LayoutNode) -> TreeNode:
    """Generate a TreeNode hierarchy for the comm"""
    data = generator.tree_data(node)
    children = []
    for item in data.get(TreeField.OPERATIONS, []):
        op_id = item.get(TreeField.OP_ID)
        if not op_id:
            continue
        op = TreeNode(
            name=item.get(TreeField.NAME),
            help=item.get(TreeField.HELP),
            operation=item.get(TreeField.OP_ID),
            function=item.get(TreeField.FUNC),
            method=item.get(TreeField.METHOD),
            path=item.get(TreeField.PATH),
        )
        children.append(op)

    for sub in node.subcommands():
        children.append(generate_tree_node(generator, sub))

    return TreeNode(
        name=data.get(TreeField.NAME),
        help=data.get(TreeField.DESCRIPTION),
        children=children,
    )


def check_for_missing(node: LayoutNode, oas: dict[str, Any]) -> dict[str, list[str]]:
    """Look for operations in node (and children) that are NOT in the OpenAPI spec"""
    def _check_missing(node: LayoutNode, ops: dict[str, Any]) -> dict[str, list[str]]:
        current = []
        for op in node.operations():
            if op.identifier not in operations:
                current.append(op.identifier)

        if not current:
            return {}
        return {node.identifier: current}


    operations = map_operations(oas.get(OasField.PATHS, {}))
    missing = _check_missing(node, operations)

    # recursively do the same for sub-commands
    for command in node.subcommands():
        missing.update(_check_missing(command, operations))

    return missing


def find_unreferenced(node: LayoutNode, oas: dict[str, Any]) -> dict[str, Any]:
    """Finds the operations in the OAS that are unrerenced by the commands."""
    def _find_operations(_node: LayoutNode) -> set[str]:
        """Recursively finds all the operations for this node and it's children"""
        current = set()
        for op in _node.operations(include_bugged=True):
            current.add(op.identifier)
        for child in _node.subcommands(include_bugged=True):
            current.update(_find_operations(child))
        return current

    referenced = _find_operations(node)
    ops = map_operations(oas.get(OasField.PATHS))
    unreferenced = {
        op_id: op_data
        for op_id, op_data in ops.items()
        if op_id not in referenced
    }

    return unreferenced


def copy_and_update(src_filename: str, dst_filename: str, replacements: dict[str, str]):
    """Copies text from src to dst with replacements of current package name to the supplied value."""
    with (
        open(src_filename, "r") as src_fp,
        open(dst_filename, "w") as dst_fp,
    ):
        # NOTE: ignore the shebangs for now... not used to copy over executable files
        dst_fp.write(COPYRIGHT)
        for line in src_fp.readlines():
            for old, new in replacements.items():
                line = line.replace(old, new)
            dst_fp.write(line)


def copy_infrastructure(dst_dir: str, package_name: str):
    """Iterates over the INFRASTRUCTURE_FILES, and copies from local to dst."""
    spath = Path(__file__).parent
    dpath = Path(dst_dir)
    replacements = {
        __package__: package_name,
    }
    for src, dst in INFRASTRUCTURE_FILES.items():
        sfile = spath / src
        dfile = dpath / dst
        copy_and_update(sfile.as_posix(), dfile.as_posix(), replacements)


def copy_tests(dst_dir: str, package_name: str):
    """Iterates over the TEST_FILES, and copies from local to dst."""
    spath = Path(__file__).parent.parent.parent / "tests" / "cli_gen"
    dpath = Path(dst_dir)
    replacements = {
        __package__: package_name,
        "tests.cli_gen": "tests",
    }
    for src, dst in TEST_FILES.items():
        sfile = spath / src
        dfile = dpath / dst
        copy_and_update(sfile.as_posix(), dfile.as_posix(), replacements)
