#!/usr/bin/env python3
"""Tiny JSON-Schema subset validator (standard library only).

Supported keywords: type, required, properties, items, enum,
minimum, maximum, minItems, minLength, additionalProperties.
Returns a list of {"path": ..., "message": ...}; empty list means valid.

CLI:
  python schemas/validate.py schemas/task_plan.schema.json path/to/plan.json
"""

import json
import os
import sys

TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "null": type(None),
}


def _type_ok(value, expected):
    want = expected if isinstance(expected, list) else [expected]
    for t in want:
        py = TYPE_MAP.get(t)
        if py is None:
            continue
        if t in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(value, schema, path="$"):
    errors = []
    if not isinstance(schema, dict):
        return errors

    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append({"path": path, "message": "expected type %s" % schema["type"]})
        return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            {"path": path, "message": "not in enum %s" % (schema["enum"],)}
        )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append({"path": path, "message": "shorter than minLength"})

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append({"path": path, "message": "below minimum"})
        if "maximum" in schema and value > schema["maximum"]:
            errors.append({"path": path, "message": "above maximum"})

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append({"path": "%s.%s" % (path, key), "message": "missing required"})
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, "%s.%s" % (path, key))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(
                        {"path": "%s.%s" % (path, key), "message": "additional property"}
                    )
        elif isinstance(schema.get("additionalProperties"), dict):
            for key in value:
                if key not in props:
                    errors += validate(value[key], schema["additionalProperties"], "%s.%s" % (path, key))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append({"path": path, "message": "fewer than minItems"})
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], "%s[%d]" % (path, i))
    return errors


def load_schema(name):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, name + ".schema.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def check(name, data):
    return validate(data, load_schema(name))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        data = json.load(f)
    errs = validate(data, schema)
    print(json.dumps(errs, ensure_ascii=False, indent=2))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
