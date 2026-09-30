"""Exact join prediction from per-key aggregates, without a joined table.

Memory is O(distinct non-NULL keys), not O(predicted output rows). Keys are exact
string tuples. Monetary amounts use arbitrary-precision integer arithmetic in
units of 10^-18, independent of the caller's Decimal context.
"""
from __future__ import annotations

from heapq import nsmallest
from pathlib import Path

from . import __version__
from .csvio import Key, TableAggregate, format_amount, read_aggregate
from .models import (
    AuditConfig,
    AuditResult,
    Expansion,
    InputError,
    MoneyStats,
    RuleResult,
    SideStats,
)


def _validate_config(config: AuditConfig) -> None:
    if config.join_type not in ('left', 'inner'):
        raise InputError('Join type must be left or inner.')
    if config.relationship not in ('one-to-one', 'one-to-many', 'many-to-one', 'many-to-many'):
        raise InputError('Expected relationship must be one-to-one, one-to-many, many-to-one, or many-to-many.')
    if not config.left_keys or len(config.left_keys) != len(config.right_keys):
        raise InputError('Select the same nonzero number of key columns for both inputs.')
    for columns in (config.left_keys, config.right_keys):
        if any(not isinstance(column, str) or column == '' for column in columns) or len(set(columns)) != len(columns):
            raise InputError('Selected key columns must be nonempty strings without repeats.')
    if not isinstance(config.delimiter, str) or len(config.delimiter) != 1 or config.delimiter in '\r\n"\x00':
        raise InputError('Delimiter must be one character other than a quote, NUL, or newline.')
    if not isinstance(config.sample_limit, int) or isinstance(config.sample_limit, bool) or not 0 <= config.sample_limit <= 100:
        raise InputError('Sample limit must be an integer from 0 to 100.')
    if config.max_output_rows is not None and (
        not isinstance(config.max_output_rows, int) or isinstance(config.max_output_rows, bool) or config.max_output_rows < 0
    ):
        raise InputError('Maximum output rows must be a nonnegative integer.')
    if any(not isinstance(value, str) for value in config.null_values):
        raise InputError('NULL literals must be strings.')
    if config.amount_column is not None and (not isinstance(config.amount_column, str) or config.amount_column == ''):
        raise InputError('Amount column must be a nonempty string.')
    if not isinstance(config.fail_on_unmatched, bool) or not isinstance(config.fail_on_expansion, bool):
        raise InputError('Unmatched and expansion rule switches must be booleans.')


def _stats(table: TableAggregate, other: TableAggregate) -> SideStats:
    unmatched_keys = 0
    unmatched_rows = table.null_rows
    duplicate_keys = 0
    duplicate_excess_rows = 0
    for key, group in table.keys.items():
        if group.rows > 1:
            duplicate_keys += 1
            duplicate_excess_rows += group.rows - 1
        if key not in other.keys:
            unmatched_keys += 1
            unmatched_rows += group.rows
    return SideStats(
        rows=table.rows,
        matchable_rows=table.rows - table.null_rows,
        null_key_rows=table.null_rows,
        distinct_matchable_keys=len(table.keys),
        duplicate_keys=duplicate_keys,
        duplicate_excess_rows=duplicate_excess_rows,
        unmatched_rows=unmatched_rows,
        unmatched_keys=unmatched_keys,
    )


def _relationship(left_unique: bool, right_unique: bool) -> str:
    if left_unique:
        return 'one-to-one' if right_unique else 'one-to-many'
    return 'many-to-one' if right_unique else 'many-to-many'


def audit(config: AuditConfig) -> AuditResult:
    """Fully validate both inputs and return exact predictions and rule results.

    ``sample_limit`` is one global key-sample budget, allocated in order to the
    ten largest expansion groups, unmatched-left keys, and unmatched-right keys.
    NULL-key rows contribute to unmatched row counts but not key counts/samples.
    """
    _validate_config(config)
    nulls = frozenset(config.null_values)
    left = read_aggregate(Path(config.left), config.left_keys, delimiter=config.delimiter,
                          null_values=nulls, side='Left', amount_column=config.amount_column)
    right = read_aggregate(Path(config.right), config.right_keys, delimiter=config.delimiter,
                           null_values=nulls, side='Right')
    left_stats = _stats(left, right)
    right_stats = _stats(right, left)
    matched_rows = 0
    expanded_rows = 0
    extra_copies = 0
    max_matches = 0
    matched_input_amount = 0
    matched_output_amount = 0
    duplicated_signed = 0
    duplicated_absolute = 0
    expansion_groups: list[tuple[int, Key, int, int]] = []
    for key, left_group in left.keys.items():
        right_group = right.keys.get(key)
        if right_group is None:
            continue
        copies = right_group.rows
        max_matches = max(max_matches, copies)
        matched_rows += left_group.rows * copies
        matched_input_amount += left_group.amount
        matched_output_amount += left_group.amount * copies
        if copies > 1:
            excess = left_group.rows * (copies - 1)
            extra_copies += excess
            expanded_rows += left_group.rows
            duplicated_signed += left_group.amount * (copies - 1)
            duplicated_absolute += left_group.absolute_amount * (copies - 1)
            expansion_groups.append((-excess, key, left_group.rows, copies))

    predicted_rows = matched_rows + (left_stats.unmatched_rows if config.join_type == 'left' else 0)
    left_unique = left_stats.duplicate_keys == 0
    right_unique = right_stats.duplicate_keys == 0
    relationship_passed = (
        (config.relationship not in ('one-to-one', 'one-to-many') or left_unique)
        and (config.relationship not in ('one-to-one', 'many-to-one') or right_unique)
    )
    rules = [RuleResult('relationship', relationship_passed,
                        'Declared uniqueness requirements are satisfied.' if relationship_passed
                        else 'Declared uniqueness requirements are violated by non-NULL keys.')]
    if config.max_output_rows is not None:
        rules.append(RuleResult('max_output_rows', predicted_rows <= config.max_output_rows,
                                f'Predicted output is {predicted_rows:,} rows; limit is {config.max_output_rows:,}.'))
    if config.fail_on_unmatched:
        rules.append(RuleResult('unmatched', left_stats.unmatched_rows + right_stats.unmatched_rows == 0,
                                f'Unmatched rows: {left_stats.unmatched_rows:,} left and {right_stats.unmatched_rows:,} right, including NULL keys.'))
    if config.fail_on_expansion:
        rules.append(RuleResult('expansion', extra_copies == 0,
                                f'The join introduces {extra_copies:,} extra copies of left rows.'))

    remaining_samples = config.sample_limit
    expansions = []
    for index, (negative_excess, key, left_rows, right_rows) in enumerate(nsmallest(10, expansion_groups), start=1):
        key_sample = list(key) if remaining_samples else None
        if remaining_samples:
            remaining_samples -= 1
        expansions.append(Expansion(f'Group {index}', left_rows, right_rows,
                                    left_rows * right_rows, -negative_excess, key_sample))
    left_samples = [list(key) for key in nsmallest(remaining_samples, (key for key in left.keys if key not in right.keys))]
    remaining_samples -= len(left_samples)
    right_samples = [list(key) for key in nsmallest(remaining_samples, (key for key in right.keys if key not in left.keys))]

    money = None
    if config.amount_column is not None:
        unmatched_amount = left.amount - matched_input_amount
        output_amount = matched_output_amount + (unmatched_amount if config.join_type == 'left' else 0)
        money = MoneyStats(
            input_total=format_amount(left.amount),
            matched_input_total=format_amount(matched_input_amount),
            unmatched_input_total=format_amount(unmatched_amount),
            output_total=format_amount(output_amount),
            duplicated_signed_amount=format_amount(duplicated_signed),
            duplicated_absolute_amount=format_amount(duplicated_absolute),
            duplicated_left_rows=expanded_rows,
            extra_copies=extra_copies,
            dropped_amount=format_amount(unmatched_amount if config.join_type == 'inner' else 0),
            net_change=format_amount(output_amount - left.amount),
        )
    return AuditResult(
        schema_version='1.0',
        tool_version=__version__,
        join_type=config.join_type,
        expected_relationship=config.relationship,
        observed_relationship=_relationship(left_unique, right_unique),
        key_columns=len(config.left_keys),
        left=left_stats,
        right=right_stats,
        predicted_rows=predicted_rows,
        matched_output_rows=matched_rows,
        expansion_rows=extra_copies,
        max_right_matches=max_matches,
        expanded_left_rows=expanded_rows,
        passed=all(rule.passed for rule in rules),
        rules=rules,
        expansions=expansions,
        money=money,
        samples_included=config.sample_limit > 0,
        unmatched_left_samples=left_samples,
        unmatched_right_samples=right_samples,
        notes=[
            'Keys are exact strings; there is no trimming, coercion, or deduplication.',
            'Any configured NULL key component prevents a match; NULL-key rows count as unmatched rows, not distinct keys.',
            'Relationship uniqueness is checked over every non-NULL key, including unmatched keys.',
            'Expansion counts extra copies of left rows; only the ten largest expansion groups are shown.',
            'Monetary values, when selected, are validated on every left row and summed exactly without rounding.',
        ],
    )
