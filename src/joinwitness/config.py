"""Versioned local rerun configurations. Unlike reports, configs contain private paths."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from .models import AuditConfig, InputError, JoinType, Relationship

_FIELDS = set(AuditConfig.__dataclass_fields__)


def dump_config(config: AuditConfig, destination: Path) -> str:
    values = asdict(config)
    for name in ('left', 'right'):
        try:
            values[name] = os.path.relpath(values[name].resolve(), destination.parent.resolve())
        except ValueError:  # Different drives on Windows.
            values[name] = str(values[name].resolve())
    return json.dumps({'schema_version': 1, **values}, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'Duplicate configuration field: {key}')
        result[key] = value
    return result


def load_config(path: Path) -> AuditConfig:
    if path.stat().st_size > 1_048_576:
        raise InputError('Configuration exceeds the 1 MiB limit.')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_reject_duplicate_fields)
    except InputError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InputError('Configuration must be valid UTF-8 JSON with bounded nesting and numbers.') from exc
    if not isinstance(data, dict):
        raise InputError('Configuration must be a JSON object.')
    unknown = set(data) - (_FIELDS | {'schema_version'})
    if unknown:
        raise InputError('Unknown configuration fields: ' + ', '.join(sorted(unknown)))
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise InputError('Configuration schema_version must be 1.')
    for name in ('left', 'right'):
        if not isinstance(data.get(name), str) or not data[name] or '\x00' in data[name]:
            raise InputError(f'Configuration {name} must be a nonempty path string without NUL characters.')
    for name in ('left_keys', 'right_keys'):
        if not isinstance(data.get(name), list) or not data[name] or any(
            not isinstance(value, str) or not value for value in data[name]
        ):
            raise InputError(f'Configuration {name} must be a nonempty list of column names.')
    if 'null_values' in data and (not isinstance(data['null_values'], list) or any(
        not isinstance(value, str) for value in data['null_values']
    )):
        raise InputError('Configuration null_values must be a list of strings.')
    for name in ('fail_on_unmatched', 'fail_on_expansion'):
        if name in data and type(data[name]) is not bool:
            raise InputError(f'Configuration {name} must be true or false.')
    if 'sample_limit' in data and type(data['sample_limit']) is not int:
        raise InputError('Configuration sample_limit must be an integer.')
    if data.get('max_output_rows') is not None and type(data['max_output_rows']) is not int:
        raise InputError('Configuration max_output_rows must be an integer or null.')
    for name in ('delimiter', 'relationship', 'join_type'):
        if name in data and not isinstance(data[name], str):
            raise InputError(f'Configuration {name} must be a string.')
    if data.get('amount_column') is not None and not isinstance(data['amount_column'], str):
        raise InputError('Configuration amount_column must be a column name or null.')
    base = path.resolve().parent
    return AuditConfig(
        left=base / data['left'], right=base / data['right'],
        left_keys=tuple(data['left_keys']), right_keys=tuple(data['right_keys']),
        relationship=cast(Relationship, data.get('relationship', 'many-to-one')),
        join_type=cast(JoinType, data.get('join_type', 'left')),
        amount_column=data.get('amount_column'), delimiter=data.get('delimiter', ','),
        null_values=tuple(data.get('null_values', [''])), sample_limit=data.get('sample_limit', 0),
        max_output_rows=data.get('max_output_rows'),
        fail_on_unmatched=data.get('fail_on_unmatched', False),
        fail_on_expansion=data.get('fail_on_expansion', False),
    )
