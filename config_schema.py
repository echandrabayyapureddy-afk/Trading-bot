"""Structural JSON Schemas; config.py also enforces semantic cross-field rules."""
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import types
from typing import Literal, Union, get_args, get_origin, get_type_hints

from config import BotConfig, ResearchManifest


def _schema(annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        return {"anyOf": [_schema(a) for a in args]}
    if origin is Literal:
        return {"enum": list(args)}
    if origin is tuple:
        return {"type": "array", "items": _schema(args[0])}
    if is_dataclass(annotation):
        hints = get_type_hints(annotation)
        return {"type": "object", "additionalProperties": False,
                "required": [f.name for f in fields(annotation)],
                "properties": {f.name: {**_schema(hints[f.name]),
                                        "description": f.metadata['reason'],
                                        "x-provenance": f.metadata['provenance']}
                               for f in fields(annotation)}}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {"type": "string", "enum": [a.value for a in annotation]}
    if annotation is Decimal:
        return {"type": "string", "pattern": r"^-?\d+(\.\d+)?$", "description": "Exact decimal string"}
    if annotation in (date, datetime):
        return {"type": "string", "format": "date" if annotation is date else "date-time"}
    return {"type": {str: "string", int: "integer", bool: "boolean", type(None): "null"}[annotation]}


def config_schema():
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "NSE Bot Configuration 1.0", **_schema(BotConfig)}


def manifest_schema():
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "NSE Bot Research Manifest 1.0", **_schema(ResearchManifest)}
