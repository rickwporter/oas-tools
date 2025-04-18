import os
from pathlib import Path
from typing import Any

from oas_tools.cli_gen.generator import COPYRIGHT
from oas_tools.cli_gen.generator import Generator
from oas_tools.cli_gen.layout_types import CommandNode
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


def generate_node(generator: Generator, node: CommandNode, directory: str) -> None:
    """Creates a file/module for the current node, and recursively goes through sub-commands."""
    text = generator.shebang()
    text += generator.copyright()
    text += generator.standard_imports()
    text += generator.subcommand_imports(node.subcommands())
    text += generator.app_definition(node)
    for command in node.operations():
        text += generator.function_definition(command)
    text += generator.main()

    filename = os.path.join(directory, to_snake_case(node.identifier) + ".py")
    with open(filename, "w") as fp:
        fp.write(text)
    os.chmod(filename, 0o755)

    # recursively do the same for sub-commands
    for command in node.subcommands():
        generate_node(generator, command, directory)


def check_for_missing(node: CommandNode, oas: dict[str, Any]) -> dict[str, list[str]]:
    """Look for operations in node (and children) that are NOT in the OpenAPI spec"""
    def _check_missing(node: CommandNode, ops: dict[str, Any]) -> dict[str, list[str]]:
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


def copy_and_update(src_filename: str, dst_filename: str, package_name: str):
    """Copies text from src to dst with replacements of current package name to the supplied value."""
    module_name = __package__
    with (
        open(src_filename, "r") as src_fp,
        open(dst_filename, "w") as dst_fp,
    ):
        # NOTE: ignore the shebangs for now... not used to copy over executable files
        dst_fp.write(COPYRIGHT)
        for line in src_fp.readlines():
            dst_fp.write(line.replace(module_name, package_name))


def copy_infrastructure(dst_dir: str, package_name: str):
    """Iterates over the INFRASTRUCTURE_FILES, and copies from local to dst."""
    spath = Path(__file__).parent
    dpath = Path(dst_dir)
    for src, dst in INFRASTRUCTURE_FILES.items():
        sfile = spath / src
        dfile = dpath / dst
        copy_and_update(sfile.as_posix(), dfile.as_posix(), package_name)
