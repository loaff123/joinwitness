"""Strict UTF-8 CSV ingestion with exact strings and bounded fields.

Python's CSV parser deliberately accepts a quote in an unquoted field, even in
strict mode. The small lexical validator below rejects that ambiguity before
passing complete physical lines to the standard parser. Embedded quoted CR/LF
and doubled quote escapes retain their original values.
"""
from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .models import InputError

MAX_FIELD_CHARS = 131_072
MAX_AMOUNT_DIGITS = 38
MAX_AMOUNT_SCALE = 18
AMOUNT_FACTOR = 10 ** MAX_AMOUNT_SCALE
_AMOUNT = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z')
Key = tuple[str, ...]


@dataclass(slots=True)
class KeyAggregate:
    rows: int = 0
    amount: int = 0
    absolute_amount: int = 0


@dataclass(slots=True)
class TableAggregate:
    keys: dict[Key, KeyAggregate] = field(default_factory=dict)
    rows: int = 0
    null_rows: int = 0
    amount: int = 0


def _strict_lines(stream: TextIO, delimiter: str, side: str) -> Iterator[str]:
    """Validate CSV quote grammar and decoded field lengths without changing it."""
    start, unquoted, quoted, after_quote = range(4)
    state = start
    field_chars = 0
    for line_number, line in enumerate(stream, start=1):
        for char in line:
            if char == '\x00':
                raise InputError(f'{side} CSV contains a NUL character at physical line {line_number}.')
            if state == quoted:
                if char == '"':
                    state = after_quote
                else:
                    field_chars += 1
            elif state == after_quote:
                if char == '"':
                    state = quoted
                    field_chars += 1
                elif char == delimiter or char in '\r\n':
                    state = start
                    field_chars = 0
                else:
                    raise InputError(f'{side} CSV has characters after a closing quote at physical line {line_number}.')
            elif char == delimiter or char in '\r\n':
                state = start
                field_chars = 0
            elif char == '"':
                if state != start:
                    raise InputError(f'{side} CSV has a quote inside an unquoted field at physical line {line_number}.')
                state = quoted
            else:
                state = unquoted
                field_chars += 1
            if field_chars > MAX_FIELD_CHARS:
                raise InputError(f'{side} CSV field exceeds the {MAX_FIELD_CHARS:,}-character limit at physical line {line_number}.')
        yield line
    if state == quoted:
        raise InputError(f'{side} CSV ends inside a quoted field.')


def _parse_amount(value: str, side: str, record_number: int) -> int:
    """Parse plain decimal notation to integer units of 10^-18; never round."""
    if _AMOUNT.fullmatch(value) is None:
        raise InputError(f'{side} CSV record {record_number} has an invalid monetary amount; use plain decimal notation.')
    unsigned = value.lstrip('+-')
    whole, _, fraction = unsigned.partition('.')
    if len(whole) + len(fraction) > MAX_AMOUNT_DIGITS or len(fraction) > MAX_AMOUNT_SCALE:
        raise InputError(
            f'{side} CSV record {record_number} has a monetary amount outside the '
            f'{MAX_AMOUNT_DIGITS}-digit / {MAX_AMOUNT_SCALE}-fractional-digit limits.'
        )
    amount: int = int((whole or '0') + fraction) * 10 ** (MAX_AMOUNT_SCALE - len(fraction))
    return -amount if value.startswith('-') else amount


def format_amount(amount: int) -> str:
    """Render exact fixed-point integer units without context-dependent rounding."""
    sign = '-' if amount < 0 else ''
    whole, fractional = divmod(abs(amount), AMOUNT_FACTOR)
    if not fractional:
        return f'{sign}{whole}'
    return f'{sign}{whole}.{fractional:018d}'.rstrip('0')


def read_aggregate(
    path: Path,
    key_columns: tuple[str, ...],
    *,
    delimiter: str,
    null_values: frozenset[str],
    side: str,
    amount_column: str | None = None,
) -> TableAggregate:
    """Read and validate one entire input, storing only per-key aggregates."""
    result = TableAggregate()
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(_strict_lines(stream, delimiter, side), delimiter=delimiter, strict=True)
            header = next(reader, None)
            if not header:
                raise InputError(f'{side} CSV must contain a nonempty header record.')
            if '' in header:
                raise InputError(f'{side} CSV contains an empty column header.')
            if len(set(header)) != len(header):
                raise InputError(f'{side} CSV contains duplicate column headers.')
            positions = {name: index for index, name in enumerate(header)}
            if any(column not in positions for column in key_columns):
                raise InputError(f'{side} CSV is missing a selected key column.')
            if amount_column is not None and amount_column not in positions:
                raise InputError(f'{side} CSV is missing the selected amount column.')
            key_positions = tuple(positions[column] for column in key_columns)
            amount_position = positions[amount_column] if amount_column is not None else None
            for record_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise InputError(
                        f'{side} CSV record {record_number} has {len(row)} fields; '
                        f'the header has {len(header)}.'
                    )
                amount = _parse_amount(row[amount_position], side, record_number) if amount_position is not None else 0
                result.rows += 1
                result.amount += amount
                key = tuple(row[position] for position in key_positions)
                if any(component in null_values for component in key):
                    result.null_rows += 1
                    continue
                aggregate = result.keys.get(key)
                if aggregate is None:
                    aggregate = KeyAggregate()
                    result.keys[key] = aggregate
                aggregate.rows += 1
                aggregate.amount += amount
                aggregate.absolute_amount += abs(amount)
    except UnicodeError as error:
        raise InputError(f'{side} CSV is not valid UTF-8.') from error
    except csv.Error as error:
        raise InputError(f'{side} CSV is malformed or exceeds the {MAX_FIELD_CHARS:,}-character field limit.') from error
    except OSError as error:
        raise InputError(f'{side} CSV could not be read ({type(error).__name__}).') from error
    return result
