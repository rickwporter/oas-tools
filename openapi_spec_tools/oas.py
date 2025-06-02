#!/usr/bin/env python3
import os
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from typing_extensions import Annotated

from openapi_spec_tools._typer import OasFilenameArgument
from openapi_spec_tools._typer import error_out
from openapi_spec_tools.types import OasField
from openapi_spec_tools.utils import count_values
from openapi_spec_tools.utils import find_diffs
from openapi_spec_tools.utils import find_paths
from openapi_spec_tools.utils import find_references
from openapi_spec_tools.utils import map_content_types
from openapi_spec_tools.utils import map_operations
from openapi_spec_tools.utils import model_filter
from openapi_spec_tools.utils import model_references
from openapi_spec_tools.utils import models_referenced_by
from openapi_spec_tools.utils import open_oas
from openapi_spec_tools.utils import remove_schema_tags
from openapi_spec_tools.utils import schema_operations_filter
from openapi_spec_tools.utils import set_nullable_not_required
from openapi_spec_tools.utils import unroll

INDENT = "    "


def short_filename(long: str) -> str:
    """Shorten the filename to just the name portion."""
    return Path(long).name


def console_factory() -> Console:
    """Utility to consolidate creation/initialization of Console.

    A little hacky here... Allow terminal width to be set directly by an environment variable, or
    when detecting that we're testing use a wide terminal to avoid line wrap issues.
    """
    width = os.environ.get("TERMINAL_WIDTH")
    pytest_version = os.environ.get("PYTEST_VERSION")
    if width is not None:
        width = int(width)
    elif pytest_version is not None:
        width = 3000
    return Console(width=width)


#################################################
# Top-level stuff
app = typer.Typer(
    name="oas",
    no_args_is_help=True,
    short_help="OpenAPI specification tools",
    help="Various utilities for inspecting, analyzing and modifying OpenAPI specifications.",
)


@app.command("info", short_help="Display the 'info' from the OpenAPI specification")
def info(
    filename: OasFilenameArgument,
) -> None:
    spec = open_oas(filename)

    info = spec.get("info", {})
    console = console_factory()
    console.print(yaml.dump({"info": info}, indent=len(INDENT)))
    return


@app.command("summary", short_help="Display summary of OAS data")
def summary(
    filename: OasFilenameArgument,
) -> None:
    spec = open_oas(filename)
    method_count = {
        'get': 0,
        'put': 0,
        'patch': 0,
        'delete': 0,
        'post': 0,
    }
    path_count = 0
    model_count = len(spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {}))
    tag_count = {}

    for path_data in spec.get(OasField.PATHS, {}).values():
        path_count += 1
        for method, operation in path_data.items():
            if method == OasField.PARAMS:
                continue

            method_count[method] += 1
            for tag in operation.get(OasField.TAGS, []):
                orig = tag_count.get(tag, 0)
                tag_count[tag] = orig + 1

    console = console_factory()
    console.print(f"OpenAPI spec ({short_filename(filename)}):")
    console.print(f"{INDENT}Models: {model_count}")
    console.print(f"{INDENT}Paths: {path_count}")
    console.print(f"{INDENT}Operation methods ({sum(method_count.values())}):")
    for k, v in method_count.items():
        console.print(f"{INDENT * 2}{k}: {v}")
    console.print(f"{INDENT}Tags ({len(tag_count)}) with operation counts:")
    for k, v in tag_count.items():
        console.print(f"{INDENT * 2}{k}: {v}")

    return


@app.command("diff", short_help="Compare two OAS files")
def diff(
    original: Annotated[
        str,
        typer.Argument(metavar="FILENAME", show_default=False, help="Original OpenAPI specification filename"),
    ],
    updated: Annotated[
        str,
        typer.Argument(metavar="FILENAME", show_default=False, help="Updated OpenAPI specification filename"),
    ],
) -> None:
    old_spec = open_oas(original)
    new_spec = open_oas(updated)

    console = console_factory()
    diffs = find_diffs(old_spec, new_spec)
    if not diffs:
        console.print(f"No differences between {short_filename(original)} and {short_filename(updated)}")
    else:
        console.print(yaml.dump(diffs, indent=len(INDENT)))
    return


class DisplayOption(str, Enum):
    NONE = "none"
    SUMMARY = "summary"
    DIFF = "diff"
    FINAL = "final"


@app.command("update", short_help="Update the OpenAPI spec")
def update(
    original_filename: OasFilenameArgument,
    updated_filename: Annotated[Optional[str], typer.Option(help="Filename for update OpenAPI spec")] = None,
    nullable_not_required: Annotated[
        bool,
        typer.Option(help="Remove 'nullable' properties from required list"),
    ] = False,
    remove_all_tags: Annotated[bool, typer.Option(help="Remove all tags")] = False,
    remove_operations: Annotated[
        Optional[list[str]],
        typer.Option("--remove-op", show_default=False, help="List of operations to remove"),
    ] = None,
    allowed_operations: Annotated[
        Optional[list[str]],
        typer.Option("--allow-op", show_default=False, help="List of operations to keep"),
    ] = None,
    display_option: Annotated[
        DisplayOption,
        typer.Option("--display", help="Shown on console at conclusion", case_sensitive=False),
    ] = DisplayOption.DIFF,
    indent: Annotated[
        int,
        typer.Option(min=1, max=10, help="Number of characters to indent on YAML display"),
    ] = len(INDENT),
) -> None:
    old_spec = open_oas(original_filename)
    updated = deepcopy(old_spec)

    if allowed_operations and remove_operations:
        error_out("cannot specify both --allow-op and --remove-op")

    if remove_all_tags:
        updated = remove_schema_tags(updated)

    if nullable_not_required:
        updated = set_nullable_not_required(updated)

    if remove_operations:
        updated = schema_operations_filter(updated, remove=set(remove_operations))

    if allowed_operations:
        updated = schema_operations_filter(updated, allow=set(allowed_operations))

    if updated_filename:
        with open(updated_filename, "w", encoding="utf-8", newline="\n") as fp:
            yaml.dump(updated, fp, indent=indent)

    console = console_factory()
    diffs = find_diffs(old_spec, updated)
    if display_option == DisplayOption.NONE:
        pass
    elif display_option == DisplayOption.FINAL:
        console.print(yaml.dump(updated, indent=indent))
    elif not diffs:
        console.print(f"No differences between {short_filename(original_filename)} and updated")
    elif display_option == DisplayOption.DIFF:
        console.print(yaml.dump(diffs, indent=indent))
    else:  # must be DisplayOption.SUMMARY:
        diff_count = count_values(diffs)
        console.print(f"Found {diff_count} differences from {short_filename(original_filename)}")

    return


##########################################
# Analyze
analyze_typer = typer.Typer(no_args_is_help=True, short_help="Tools for analyzing an OAS file")
app.add_typer(analyze_typer, name="analyze")


##########################################
# Operations
op_typer = typer.Typer(no_args_is_help=True, short_help="Inspect things related to operations")
analyze_typer.add_typer(op_typer, name="ops")


@op_typer.command(name="list", short_help="List operations in OpenAPI spec")
def operation_list(
    filename: OasFilenameArgument,
    search: Annotated[
        Optional[str],
        typer.Option("--contains", help="Search for this value in the operation names"),
    ] = None,
) -> None:
    spec = open_oas(filename)

    operations = map_operations(spec.get(OasField.PATHS, {}))
    names = sorted(operations.keys())
    if search:
        needle = search.lower()
        names = [_ for _ in names if needle in _.lower()]

    console = console_factory()
    match_info = f" matching '{search}'" if search else ""
    if not names:
        console.print(f"No operations found{match_info}")
    else:
        console.print(f"Found {len(names)} operations{match_info}:")
        for n in names:
            console.print(f"{INDENT}{n}")

    return


@op_typer.command(name="show", short_help="Show the opertions schema")
def operation_show(
    filename: OasFilenameArgument,
    operation_name: Annotated[str, typer.Argument(help="Name of the operation to show")],
) -> None:
    spec = open_oas(filename)

    operations = map_operations(spec.get(OasField.PATHS, {}))
    operation = operations.get(operation_name)
    if not operation:
        error_out(f"failed to find {operation_name}")

    path = operation.pop(OasField.X_PATH)
    path_params = operation.pop(OasField.X_PATH_PARAMS, None)
    method = operation.pop(OasField.X_METHOD)
    inner = {}
    if path_params:
        inner["params"] = path_params
    inner[method] = operation

    console = console_factory()
    console.print(yaml.dump({path: inner}, indent=len(INDENT)))
    return


@op_typer.command(name="models", short_help="List the models referenced by the specified operaton")
def operation_models(
    filename: OasFilenameArgument,
    operation_name: Annotated[str, typer.Argument(help="Name of the operation")],
) -> None:
    spec = open_oas(filename)

    operations = map_operations(spec.get(OasField.PATHS, {}))
    operation = operations.get(operation_name)
    if not operation:
        error_out(f"failed to find {operation_name}")

    op_references = find_references(operation)
    models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
    matches = model_filter(models, op_references)

    console = console_factory()
    if not matches:
        console.print(f"{operation_name} does not reference any models")
    else:
        console.print(f"Found {operation_name} uses {len(matches)} models:")
        for n in sorted(matches):
            console.print(f"{INDENT}{n}")

    return


##########################################
# Paths
path_typer = typer.Typer(no_args_is_help=True, short_help="Inspect things related to paths")
analyze_typer.add_typer(path_typer, name="paths")

PathSearchOption = Annotated[Optional[str], typer.Option("--contains", help="Search for this value in the path")]
PathSubpathOption = Annotated[
    bool,
    typer.Option("--sub-paths", help="Include sub-paths of the search value"),
]
PathModelsOption = Annotated[bool, typer.Option("--models", help="Include the referenced models")]

@path_typer.command(name="list", short_help="List paths in OpenAPI spec")
def paths_list(
    filename: OasFilenameArgument,
    search: PathSearchOption = None,
    include_subpaths: PathSubpathOption = False,
) -> None:
    spec = open_oas(filename)

    paths = find_paths(spec.get(OasField.PATHS, {}), search, include_subpaths)
    names = sorted(paths.keys())

    match_info = ""
    if search:
        match_info = f" matching '{search}'"
        if include_subpaths:
            match_info += " including sub-paths"

    console = console_factory()
    if not names:
        console.print(f"No paths found{match_info}")
    else:
        console.print(f"Found {len(names)} paths{match_info}:")
        for n in names:
            console.print(f"{INDENT}{n}")

    return


@path_typer.command(name="show", short_help="Show the path schema")
def paths_show(
    filename: OasFilenameArgument,
    path_name: Annotated[str, typer.Argument(help="Name of the path to show")],
    include_subpaths: PathSubpathOption = False,
    include_models: PathModelsOption = False,
) -> None:
    spec = open_oas(filename)

    paths = find_paths(spec.get(OasField.PATHS, {}), path_name, include_subpaths)
    if not paths:
        error_out(f"failed to find {path_name}")

    if include_models:
        references = find_references(paths)
        models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
        used = model_filter(models, references)
        results = {
            OasField.PATHS.value: paths,
            OasField.COMPONENTS.value: {OasField.SCHEMAS.value: used}
        }
        paths = results

    console = console_factory()
    console.print(yaml.dump(paths, indent=len(INDENT)))
    return



@path_typer.command(name="ops", short_help="Show the operations in the specified path")
def paths_operations(
    filename: OasFilenameArgument,
    path_name: Annotated[str, typer.Option(help="Name of the path to show")],
    include_subpaths: PathSubpathOption = False,
) -> None:
    spec = open_oas(filename)

    result = {}
    paths = find_paths(spec.get(OasField.PATHS, {}), path_name, include_subpaths)
    for path, path_data in paths.items():
        for method, op_data in path_data.items():
            if method == OasField.PARAMS:
                continue
            op_id = op_data.get(OasField.OP_ID)
            items = result.get(path, []) + [op_id]
            result[path] = items

    if not result:
        error_out(f"failed to find {path_name}")

    console = console_factory()
    console.print(yaml.dump(result, indent=len(INDENT)))
    return


##########################################
# Models
models_typer = typer.Typer(no_args_is_help=True, short_help="Inspect things related to models")
analyze_typer.add_typer(models_typer, name="models")

@models_typer.command(name="list", short_help="List models in OpenAPI spec")
def models_list(
    filename: OasFilenameArgument,
    search: Annotated[
        Optional[str],
        typer.Option("--contains", help="Search for this value in the model names"),
    ] = None,
) -> None:
    spec = open_oas(filename)

    names = sorted(spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {}).keys())
    if search:
        needle = search.lower()
        names = [_ for _ in names if needle in _.lower()]

    console = console_factory()
    match_info = f" matching '{search}'" if search else ""
    if not names:
        console.print(f"No models found{match_info}")
    else:
        console.print(f"Found {len(names)} models{match_info}:")
        for n in names:
            console.print(f"{INDENT}{n}")

    return


@models_typer.command(name="show", short_help="Show the model schema")
def models_show(
    filename: OasFilenameArgument,
    model_name: Annotated[str, typer.Argument(help="Name of the model to show")],
    include_referenced: Annotated[bool, typer.Option("--references", help="Include referenced models")] = False,
) -> None:
    spec = open_oas(filename)

    model = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {}).get(model_name)
    if not model:
        error_out(f"failed to find {model_name}")

    if not include_referenced:
        models = {model_name: model}
    else:
        models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
        models = model_filter(models, set([model_name]))

    console = console_factory()
    console.print(yaml.dump(models, indent=len(INDENT)))
    return


@models_typer.command(name="uses", short_help="List sub-models used by the specified model")
def models_uses(
    filename: OasFilenameArgument,
    model_name: Annotated[str, typer.Argument(help="Name of the model to show")],
) -> None:
    spec = open_oas(filename)

    models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
    if model_name not in models:
        error_out(f"no model '{model_name}' found")

    references = model_references(models)

    console = console_factory()
    matches = unroll(references, references.get(model_name))
    if not matches:
        console.print(f"{model_name} does not use any other models")
    else:
        console.print(f"Found {model_name} uses {len(matches)} models:")
        for n in sorted(matches):
            console.print(f"{INDENT}{n}")

    return


@models_typer.command(name="used-by", short_help="List models which reference the specified model")
def models_used_by(
    filename: OasFilenameArgument,
    model_name: Annotated[str, typer.Argument(help="Name of the model to show")],
) -> None:
    spec = open_oas(filename)

    models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
    if model_name not in models:
        error_out(f"no model '{model_name}' found")

    console = console_factory()
    matches = models_referenced_by(models, model_name)
    if not matches:
        console.print(f"{model_name} is not used by any other models")
    else:
        console.print(f"Found {model_name} is used by {len(matches)} models:")
        for n in sorted(matches):
            console.print(f"{INDENT}{n}")

    return


@models_typer.command(name="ops", short_help="List operations which reference the specified model")
def models_operations(
    filename: OasFilenameArgument,
    model_name: Annotated[str, typer.Argument(help="Name of the model to search for")],
) -> None:
    spec = open_oas(filename)

    models = spec.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
    if model_name not in models:
        error_out(f"no model '{model_name}' found")

    model_refs = models_referenced_by(models, model_name)
    model_refs.add(model_name)  # include the direct references, too

    matches = []
    for path_data in spec.get(OasField.PATHS, {}).values():
        for method, op_data in path_data.items():
            if method == OasField.PARAMS:
                continue
            references = find_references(op_data)
            if references.intersection(model_refs):
                op_id = op_data.get(OasField.OP_ID)
                matches.append(op_id)

    console = console_factory()
    console.print(f"Found {model_name} is used by {len(matches)} operations:")
    for n in sorted(matches):
        console.print(f"{INDENT}{n}")

    return


##########################################
# Tags
tag_typer = typer.Typer(no_args_is_help=True, short_help="Inspect things related to tags")
analyze_typer.add_typer(tag_typer, name="tags")

@tag_typer.command(name="list", short_help="List tags in OpenAPI spec")
def tags_list(
    filename: OasFilenameArgument,
    search: Annotated[Optional[str], typer.Option("--contains", help="Search for this value in the tag names")] = None,
) -> None:
    spec = open_oas(filename)

    # NOTE: not all OAS's include a "tags" section, so walk the operations

    tags = set()
    for path_data in spec.get(OasField.PATHS, {}).values():
        for method, operation in path_data.items():
            if method == OasField.PARAMS:
                continue

            for t in operation.get(OasField.TAGS):
                tags.add(t)

    names = sorted(tags)
    if search:
        needle = search.lower()
        names = [_ for _ in names if needle in _.lower()]

    console = console_factory()
    match_info = f" matching '{search}'" if search else ""
    if not names:
        console.print(f"No tags found{match_info}")
    else:
        console.print(f"Found {len(names)} tags{match_info}:")
        for n in names:
            console.print(f"{INDENT}{n}")

    return


@tag_typer.command(name="show", short_help="Show the tag schema")
def tags_show(
    filename: OasFilenameArgument,
    tag_name: Annotated[str, typer.Argument(help="Name of the tag to show")],
) -> None:
    spec = open_oas(filename)

    operations = {}
    for path, path_data in spec.get(OasField.PATHS, {}).items():
        params = path_data.get(OasField.PARAMS)
        for method, operation in path_data.items():
            if method == OasField.PARAMS:
                continue

            if tag_name in operation.get(OasField.TAGS):
                op_id = operation.get(OasField.OP_ID)
                operation[OasField.X_PATH] = path
                operation[OasField.X_METHOD] = method
                operation[OasField.X_PATH_PARAMS] = params
                operations[op_id] = operation

    if not operations:
        error_out(f"failed to find {tag_name}")

    console = console_factory()
    names = sorted(operations.keys())
    console.print(f"Tag {tag_name} has {len(names)} operations:")
    for n in names:
        console.print(f"{INDENT}{n}")
    return


##########################################
# Content-type
content_typer = typer.Typer(no_args_is_help=True, short_help="Inspect things related to content-types")
analyze_typer.add_typer(content_typer, name="content")

@content_typer.command("list", short_help="List operations by response content-type")
def content_type_list(
    filename: OasFilenameArgument,
    max_size: Annotated[int, typer.Option(help="Maximum number of operations to show")] = 10,
    content_type: Annotated[Optional[str], typer.Option(help="Only display for specified content type")] = None,
) -> None:
    spec = open_oas(filename)
    content = map_content_types(spec)

    if content_type:
        content = {k: v for k, v in content.items() if k == content_type}

    console = console_factory()
    if not content:
        console.print("No content-types found")
        return

    for name, operations in content.items():
        console.print(name)
        for op_id in sorted(list(operations))[:max_size]:
            console.print(f"    {op_id}")
        if len(operations) > max_size:
            console.print("    ...")
            console.print(f"    + {len(operations) - max_size} more")


if __name__ == "__main__":
    app()
