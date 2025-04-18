from copy import deepcopy
from datetime import datetime
from typing import Any
from typing import Optional

from oas_tools.cli_gen.layout_types import CommandNode
from oas_tools.cli_gen.utils import maybe_quoted
from oas_tools.cli_gen.utils import to_snake_case
from oas_tools.types import ContentType
from oas_tools.types import OasField
from oas_tools.utils import map_operations

NL = "\n"
SEP1 = "\n    "
SEP2 = "\n        "
SHEBANG = """\
#!/usr/bin/env python3
"""
COPYRIGHT = f"""\
# Copyright {datetime.now().year}
#
# This code was generated by the oas-tools CLI generator, DO NOT EDIT
#
"""


class Generator:
    def __init__(self, package_name: str, oas: dict[str, Any]):
        self.package_name = package_name
        self.operations = map_operations(oas.get(OasField.PATHS, {}))
        self.models = oas.get(OasField.COMPONENTS, {}).get(OasField.SCHEMAS, {})
        self.default_host = ""
        servers = oas.get(OasField.SERVERS)
        if servers:
            self.default_host = servers[0].get(OasField.URL, "")
        # ordered list of supported types
        self.supported = [
            ContentType.APP_JSON,
        ]

    def shebang(self) -> str:
        """Returns the shebang line that goes at the top of each file."""
        return SHEBANG

    def copyright(self) -> str:
        """Returns the copyright header near the top of each file."""
        return COPYRIGHT

    def standard_imports(self) -> str:
        return f"""
from enum import Enum
from typing import Optional
from typing_extensions import Annotated

import typer

from {self.package_name} import _arguments as _a
from {self.package_name} import _display as _d
from {self.package_name} import _exceptions as _e
from {self.package_name} import _logging as _l
from {self.package_name} import _requests as _r
"""

    def subcommand_imports(self, subcommands: list[CommandNode]) -> str:
        return NL.join(
            f"from {self.package_name}.{to_snake_case(n.identifier)} import app as {to_snake_case(n.identifier)}"
            for n in subcommands
        )

    def app_definition(self, node: CommandNode) -> str:
        result = f"""

app = typer.Typer(no_args_is_help=True, help="{node.description}")
"""
        for child in node.subcommands():
            result += f"""\
app.add_typer({to_snake_case(child.identifier)}, name="{child.command}")
"""

        return result

    def main(self) -> str:
        return """

if __name__ == "__main__":
    app()
"""

    def op_short_help(self, operation: dict[str, Any]) -> str:
        """Gets the short help for the operation."""
        summary = operation.get(OasField.SUMMARY)
        if summary:
            return summary

        description = operation.get(OasField.DESCRIPTION, "")
        return description.split(". ")[0]

    def op_long_help(self, operation: dict[str, Any]) -> str:
        text = operation.get(OasField.DESCRIPTION) or operation.get(OasField.SUMMARY) or ""
        # TODO: sanitize  NL's, long text, etc
        return text

    def op_request_content(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Get the `content` (if any) from the `requestBody`."""
        return operation.get(OasField.REQ_BODY, {}).get(OasField.CONTENT, {})

    def op_get_content_type(self, operation: dict[str, Any]) -> Optional[str]:
        """Get the first content-type matching a supported type."""
        content = self.op_request_content(operation)
        for ct in self.supported:
            if ct.value in content:
                return ct.value
        return None

    def op_get_body(self, operation: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Get the first body matching a supported type."""
        content = self.op_request_content(operation)
        for ct in self.supported:
            body = content.get(ct.value)
            if body:
                return body

        return None

    def op_get_settable_body_properties(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Get a dictionary of settable body propertiess"""
        body = self.op_get_body(operation)
        if not body:
            return {}

        schema = body.get(OasField.SCHEMA, {})
        ref = schema.get(OasField.REFS)
        if ref:
            schema = self.get_reference_model(ref)
        required = schema.get(OasField.REQUIRED, [])
        properties = {}
        for name, data in schema.get(OasField.PROPS, {}).items():
            if not data.get(OasField.READ_ONLY, False):
                updated = deepcopy(data)
                updated[OasField.REQUIRED] = name in required
                properties[name] = updated

        return properties

    def get_reference_model(self, full_name: str) -> dict[str, Any]:
        """Returns the reference"""
        short_name = full_name.split('/')[-1]
        return self.models.get(short_name)

    def op_infra_arguments(self, operation: dict[str, Any], command: CommandNode) -> list[str]:
        args = [
            f'_api_host: _a.ApiHostOption = "{self.default_host}"',
            '_api_key: _a.ApiKeyOption = None',
            '_api_timeout: _a.ApiTimeoutOption = 5',
            '_log_level: _a.LogLevelOption = _a.LogLevel.WARN',
            '_out_fmt: _a.OutputFormatOption = _a.OutputFormat.TABLE',
            '_out_style: _a.OutputStyleOption = _a.OutputStyle.ALL',
        ]
        if command.summary_fields:
            args.append('_details: _a.DetailsOption = False')
        return args

    def schema_to_type(self, schema: str, fmt: Optional[str]) -> str:
        """
        Gets the base Python type for simple schema types.

        The fmt is really the "format" field, but renamed to avoid masking builtin.
        """
        if schema == "boolean":
            return "bool"
        if schema == "integer":
            return "int"
        if schema == "numeric":
            return "float"
        if schema == "string":
            if fmt == "date-time":
                return "datetime"
            # TODO: uuid
            return "str"

        message = f"Unable to determine type for {schema}"
        if fmt:
            message += f" ({fmt})"
        raise ValueError(message)

    def op_params(self, operation: dict[str, Any], location: str) -> list[dict[str, Any]]:
        """
        Gets a complete list of operation parameters matching location.
        """
        params = []
        # NOTE: start with "higher level" path params, since they're more likely to be required
        for item in operation.get(OasField.X_PATH_PARAMS) or []:
            if item.get(OasField.IN) != location:
                continue
            params.append(item)
        for item in operation.get(OasField.PARAMS) or []:
            if item.get(OasField.IN) != location:
                continue
            params.append(item)
        return params

    def op_param_to_argument(self, param: dict[str, Any], allow_required: bool) -> str:
        """
        Converts a parameter into a typer argument.
        """
        var_name = to_snake_case(param.get(OasField.NAME))
        description = param.get(OasField.DESCRIPTION) or ""
        required = param.get(OasField.REQUIRED, False)
        schema = param.get(OasField.SCHEMA, {})
        schema_default = schema.get(OasField.DEFAULT)
        schema_type = schema.get(OasField.TYPE)
        schema_format = schema.get(OasField.FORMAT)
        arg_type = self.schema_to_type(schema_type, schema_format)

        typer_args = []
        if arg_type in ("int", "float"):
            schema_min = schema.get(OasField.MIN)
            if schema_min is not None:
                typer_args.append(f"min={schema_min}")
            schema_max = schema.get(OasField.MAX)
            if schema_max is not None:
                typer_args.append(f"max={schema_max}")
        if allow_required and required and schema_default is None:
            typer_type = 'typer.Argument'
            typer_args.append('show_default=False')
            arg_default = ""
        else:
            typer_type = 'typer.Option'
            if schema_default is None:
                arg_type = f"Optional[{arg_type}]"
                arg_default = " = None"
                typer_args.append('show_default=False')
            else:
                if arg_type in ("str", "datetime"):
                    arg_default = f' = "{schema_default}"'
                else:
                    arg_default = f" = {schema_default}"
        typer_args.append(f'help="{description}"')
        comma = ', '

        return f'{var_name}: Annotated[{arg_type}, {typer_type}({comma.join(typer_args)})]{arg_default}'

    def op_path_arguments(self, operation: dict[str, Any]) -> list[str]:
        """
        Converts all path parameters into typer arguments.
        """
        args = []
        path_params = self.op_params(operation, "path")
        for param in path_params:
            arg = self.op_param_to_argument(param, allow_required=True)
            args.append(arg)

        return args

    def op_query_arguments(self, operation: dict[str, Any]) -> list[str]:
        """
        Converts query parameters to typer arguments
        """
        args = []
        path_params = self.op_params(operation, "query")
        for param in path_params:
            arg = self.op_param_to_argument(param, allow_required=False)
            args.append(arg)

        return args

    def op_body_arguments(self, operation: dict[str, Any]) -> list[str]:
        args = []
        properties = self.op_get_settable_body_properties(operation)
        if not properties:
            return args

        for prop_name, prop_data in properties.items():
            py_type = self.schema_to_type(prop_data.get(OasField.TYPE), prop_data.get(OasField.FORMAT))
            if not prop_data.get(OasField.REQUIRED):
                py_type = f"Optional[{py_type}]"

            def_val = maybe_quoted(prop_data.get(OasField.DEFAULT))
            t_args = {}
            if def_val is not None:
                t_args["show_default"] = False
            help = prop_data.get(OasField.DESCRIPTION)
            if help:
                t_args['help'] = f'"{help}"'
            t_decl = f"typer.Option({', '.join([f'{k}={v}' for k, v in t_args.items()])})"
            arg = f"{to_snake_case(prop_name)}: Annotated[{py_type}, {t_decl}] = {def_val}"
            args.append(arg)

        return args

    def op_arguments(self, operation: dict[str, Any], command: CommandNode) -> str:
        args = []
        args.extend(self.op_path_arguments(operation))
        args.extend(self.op_query_arguments(operation))
        args.extend(self.op_body_arguments(operation))
        args.extend(self.op_infra_arguments(operation, command))

        return f"{NL}    " + f",{NL}    ".join(args) + f",{NL}"

    def op_url_params(self, path: str) -> str:
        """Parse the X-PATH to list the parameters that go into the URL formation."""
        parts = path.split("/")
        items = []
        last = None
        for p in parts:
            if "{" in p:
                if last:
                    items.append(f'"{last}"')
                items.append(to_snake_case(p.replace("{", "").replace("}", "")))
                last = None
            elif not last:
                last = p
            else:
                last += "/" + p
        if last:
            items.append(f'"{last}"')

        return f"_api_host, {', '.join(items)}"

    def op_param_formation(self, operation: dict[str, Any]) -> str:
        """Create the query parameters that go into the request"""
        total_params = self.op_params(operation, "query")
        result = "{}"
        for param in total_params:
            name = param.get(OasField.NAME)
            if param.get(OasField.REQUIRED, False):
                result += f"""
    params["{name}"] = {to_snake_case(name)}\
"""
            else:
                result += f"""
    if {to_snake_case(name)} is not None:
        params["{name}"] = {to_snake_case(name)}\
"""
        return result

    def op_content_header(self, operation: dict[str, Any]) -> str:
        """Returns the content-type with variable name prefix (when appropriate)"""
        content_type = self.op_get_content_type(operation)
        if not content_type:
            return ""
        return f', content_type="{content_type}"'

    def op_body_formation(self, operation: dict[str, Any]) -> str:
        """Creates a body parameter and poulates it when there are body paramters."""
        properties = self.op_get_settable_body_properties(operation)
        if not properties:
            return ""

        lines = ["body = {}"]
        for prop_name, prop_data in properties.items():
            var_name = to_snake_case(prop_name)
            if prop_data.get(OasField.REQUIRED):
                lines.append(f'body["{prop_name}"] = {var_name}')
            else:
                lines.append(f'if {var_name} is not None:')
                lines.append(f'    body["{prop_name}"] = {var_name}')

        return SEP1 + SEP1.join(lines)

    def op_check_missing(self, operation: dict[str, Any]) -> str:
        """Checks for missing required parameters"""
        lines = ["[]"]
        lines.append("if _api_key is None:")
        lines.append('    missing.append("--api-key")')

        path_params = self.op_params(operation, "query")
        for param in path_params:
            if param.get(OasField.REQUIRED, False):
                var_name = to_snake_case(param.get(OasField.NAME))
                option = '--' + var_name.replace('_', '-')
                lines.append(f'if {var_name} is None:')
                lines.append(f'    missing.append("{option}")')

        properties = self.op_get_settable_body_properties(operation)
        for prop_name, prop_data in properties.items():
            if prop_data.get(OasField.REQUIRED):
                var_name = to_snake_case(prop_name)
                option = '--' + var_name.replace('_', '-')
                lines.append(f'if {var_name} is None:')
                lines.append(f'    missing.append("{option}")')

        return SEP1.join(lines)

    def summary_display(self, node: CommandNode) -> str:
        if not node.summary_fields:
            return ""

        lines = ["if not _details:"]
        args = [maybe_quoted(v) for v in node.summary_fields]
        lines.append(f'    data = summary(data, [{', '.join(args)}])')
        return SEP2 + SEP2.join(lines)

    def function_definition(self, node: CommandNode) -> str:
        op = self.operations.get(node.identifier)
        method = op.get(OasField.X_METHOD).upper()
        path = op.get(OasField.X_PATH)
        req_args = [
            f'"{method}"',
            "url",
            "headers=headers",
            "params=params",
        ]
        if self.op_get_content_type(op):
            req_args.append("body=body")
        req_args.append("timemout=_api_timeout")

        return f"""

@app.command("{node.command}", help="{self.op_short_help(op)}")
def {to_snake_case(node.identifier)}({self.op_arguments(op, node)}) -> None:
    '''
    {self.op_long_help(op)}
    '''
    # handler for {node.identifier}: {method} {path}
    _l.init_logging(_log_level)
    headers = _r.request_headers(_api_key{self.op_content_header(op)})
    url = _r.create_url({self.op_url_params(path)})
    missing = {self.op_check_missing(op)}
    if missing:
        _e.handle_exceptions(_e.MissingRequiredError(missing))

    params = {self.op_param_formation(op)}{self.op_body_formation(op)}

    try:
        data = _r.request({', '.join(req_args)}){self.summary_display(node)}
        _d.display(data, _out_fmt, _out_style)
    except Exception as ex:
        _e.handle_exceptions(ex)

    return
"""
