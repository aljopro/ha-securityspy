#!/usr/bin/env python3
"""Validate the OpenAPI description, rejecting duplicate keys.

`openapi_spec_validator` alone is not enough. It loads through PyYAML, which
resolves a duplicate mapping key by silently keeping the last one -- so a file
carrying two `description:` keys on one operation validates cleanly as OpenAPI
3.1 while quietly discarding the first value. That is not hypothetical: this
description shipped for a time with two descriptions on `/++settings-cameras`,
and the `format=json` requirement was the half being thrown away. A strict
parser (js-yaml, used by most editor extensions) rejects the same file outright,
so the bug showed up as "my Swagger extension won't open it" rather than as a
failing check.

This runs both gates: strict YAML first, then OpenAPI validation.

Usage:
    uv run --directory aiosecurityspy python ../scripts/validate_openapi.py
    scripts/validate_openapi.py [PATH]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from openapi_spec_validator import validate

DEFAULT = Path(__file__).resolve().parent.parent / "aiosecurityspy/docs/securityspy-openapi.yaml"

#: Every operation must say what evidence stands behind it.
VERIFICATION_VALUES = {"live-6.21", "client-source", "research-only"}


class StrictLoader(yaml.SafeLoader):
    """A SafeLoader that treats a duplicate mapping key as an error."""


def _no_duplicate_keys(loader: StrictLoader, node: yaml.MappingNode, *, deep: bool = False) -> dict:
    """Construct a mapping, raising if any key appears twice."""
    seen: set[object] = set()
    for key_node, _value in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def main() -> int:
    """Run every gate over the description; return a process exit code."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.is_file():
        print(f"not found: {path}", file=sys.stderr)
        return 1

    try:
        # StrictLoader subclasses SafeLoader; it only adds duplicate-key detection.
        spec = yaml.load(path.read_text(encoding="utf-8"), StrictLoader)  # noqa: S506
    except yaml.YAMLError as exc:
        print(f"FAIL strict YAML: {exc}", file=sys.stderr)
        return 1
    print("ok   strict YAML (no duplicate keys)")

    try:
        validate(spec)
    except Exception as exc:  # noqa: BLE001 - the validator raises several types
        print(f"FAIL OpenAPI: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("ok   OpenAPI 3.1")

    missing = [
        f"{method.upper()} {route}"
        for route, item in (spec.get("paths") or {}).items()
        for method, operation in item.items()
        if isinstance(operation, dict) and "x-verification" not in operation
    ]
    bad = [
        f"{method.upper()} {route} -> {operation['x-verification']!r}"
        for route, item in (spec.get("paths") or {}).items()
        for method, operation in item.items()
        if isinstance(operation, dict)
        and operation.get("x-verification") not in VERIFICATION_VALUES
        and "x-verification" in operation
    ]
    if missing or bad:
        for entry in missing:
            print(f"FAIL missing x-verification: {entry}", file=sys.stderr)
        for entry in bad:
            print(f"FAIL unknown x-verification: {entry}", file=sys.stderr)
        return 1
    print("ok   every operation carries a known x-verification")
    return 0


if __name__ == "__main__":
    sys.exit(main())
