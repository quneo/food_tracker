"""Pydantic JSON Schema -> the strict subset that structured outputs accept.

Strict mode wants every object closed (additionalProperties: false) with all properties
required (optional ones are nullable instead), no oneOf/const/defaults, and plain
references. Definitions are inlined: our models are not recursive."""

from typing import Any

from pydantic import BaseModel

DROP = {
    "title",
    "default",
    "examples",
    "discriminator",
    "format",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
}


def strict_schema(model: type[BaseModel]) -> dict:
    raw = model.model_json_schema()
    definitions = raw.pop("$defs", {})

    def convert(node: Any) -> Any:
        if isinstance(node, list):
            return [convert(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = definitions[node["$ref"].split("/")[-1]]
            extra = {key: value for key, value in node.items() if key != "$ref"}
            return convert({**target, **extra})
        result = {}
        for key, value in node.items():
            if key in DROP:
                continue
            if key == "oneOf":
                key = "anyOf"
            if key == "const":
                result["enum"] = [value]
                continue
            if key == "properties":
                result[key] = {name: convert(prop) for name, prop in value.items()}
                continue
            result[key] = convert(value)
        if result.get("type") == "object" or "properties" in result:
            result["type"] = "object"
            result["additionalProperties"] = False
            result["required"] = list(result.get("properties", {}))
        return result

    return convert(raw)
