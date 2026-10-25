from importlib import resources
from typing import Any

from ..config import Config
from ..tools import available_tools, render_available

_PROMPTS = resources.files("brickwright.prompts")


def system_prompt(config: Config | None = None, *, external: bool = False) -> str:
    """Assemble the (internal or external) agent's system prompt."""
    from bricklayer import api_reference

    is_subagent = config is not None and config.is_subagent
    parts = [_get_prompt("general_instructions")]
    if not external:
        internal = _get_prompt("internal_agent_instructions")
        internal = internal.replace("{tool_descriptions}", _tool_descriptions(config))
        internal = internal.replace("{render_guidance}", _render_guidance())
        internal = internal.replace("{subagent_guidance}", _dispatch_guidance(config))
        parts.append(internal)
        if is_subagent:
            parts.append(_get_prompt("internal_subagent_instructions"))
    parts.append(api_reference())
    return "\n".join(parts)


def _get_prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text()


def _tool_descriptions(config: Config | None) -> str:
    """Render the available tools for the system prompt."""
    blocks = []
    for tool in available_tools(config):
        fn = tool["function"]
        schema = fn["parameters"]
        params = ", ".join(schema["properties"])
        block = [f"### `{fn['name']}({params})`", "", fn["description"]]
        param_lines = _param_lines(schema, indent=0)
        if param_lines:
            block.extend(["", "Args:", *param_lines])
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def _type_label(schema: dict[str, Any]) -> str:
    """A short type annotation for a parameter, e.g. ``array of object``."""
    if "anyOf" in schema:
        return " | ".join(_type_label(option) for option in schema["anyOf"])
    kind = schema.get("type", "any")
    if kind == "array":
        kind = f"array of {_type_label(schema.get('items', {}))}"
    if "enum" in schema:
        kind += f", one of: {', '.join(map(str, schema['enum']))}"
    return kind


def _param_lines(schema: dict[str, Any], indent: int) -> list[str]:
    """Render an object schema's properties."""
    required = set(schema.get("required", []))
    lines = []
    for name, prop in schema.get("properties", {}).items():
        pad = "  " * indent
        parts = [f"{pad}- `{name}` ({_type_label(prop)})"]
        if name not in required:
            parts.append(" (optional)")
        desc = prop.get("description") or next(
            (
                option["description"]
                for option in prop.get("anyOf", [])
                if "description" in option
            ),
            None,
        )
        if desc:
            parts.append(f": {desc}")
        line = "".join(parts)
        fields = _fields_of(prop, indent + 1)
        if fields:
            line += _shape_lead_in(prop, after=line)
        lines.append(line)
        lines.extend(fields)
    return lines


def _shape_lead_in(prop: dict[str, Any], *, after: str) -> str:
    """Sentence that flags the nested bullets as the object's field list."""
    each = "Each element is" if prop.get("type") == "array" else "It is"
    sentence = f"{each} an object with these fields:"
    sep = " " if after.rstrip().endswith((".", ":", "!", "?")) else ". "
    return f"{sep}{sentence}"


def _fields_of(prop: dict[str, Any], indent: int) -> list[str]:
    """Nested field bullets for an object-typed (or array-of-object) parameter."""
    target = prop.get("items", {}) if prop.get("type") == "array" else prop
    if target.get("type") == "object" and "properties" in target:
        return _param_lines(target, indent)
    return []


def _render_guidance() -> str:
    return _get_prompt("render_guidance") if render_available() else ""


def _dispatch_guidance(config: Config | None) -> str:
    if config is None or not config.can_dispatch_subagents:
        return ""
    return _get_prompt("dispatch_guidance")
