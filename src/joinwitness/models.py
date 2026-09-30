"""Stable configuration and report contracts for JoinWitness 0.1."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Relationship = Literal['one-to-one', 'one-to-many', 'many-to-one', 'many-to-many']
JoinType = Literal['inner', 'left']

class InputError(ValueError):
    """Invalid or unreadable input; safe to show to the local CLI user."""

@dataclass(frozen=True)
class AuditConfig:
    left: Path
    right: Path
    left_keys: tuple[str, ...]
    right_keys: tuple[str, ...]
    relationship: Relationship = 'many-to-one'
    join_type: JoinType = 'left'
    amount_column: str | None = None
    delimiter: str = ','
    null_values: tuple[str, ...] = ('',)
    sample_limit: int = 0
    max_output_rows: int | None = None
    fail_on_unmatched: bool = False
    fail_on_expansion: bool = False

@dataclass(frozen=True)
class SideStats:
    rows: int
    matchable_rows: int
    null_key_rows: int
    distinct_matchable_keys: int
    duplicate_keys: int
    duplicate_excess_rows: int
    unmatched_rows: int
    unmatched_keys: int

@dataclass(frozen=True)
class RuleResult:
    code: str
    passed: bool
    message: str

@dataclass(frozen=True)
class Expansion:
    group: str
    left_rows: int
    right_rows: int
    output_rows: int
    extra_left_copies: int
    key: list[str] | None = None

@dataclass(frozen=True)
class MoneyStats:
    input_total: str
    matched_input_total: str
    unmatched_input_total: str
    output_total: str
    duplicated_signed_amount: str
    duplicated_absolute_amount: str
    duplicated_left_rows: int
    extra_copies: int
    dropped_amount: str
    net_change: str

@dataclass(frozen=True)
class AuditResult:
    schema_version: str
    tool_version: str
    join_type: str
    expected_relationship: str
    observed_relationship: str
    key_columns: int
    left: SideStats
    right: SideStats
    predicted_rows: int
    matched_output_rows: int
    expansion_rows: int
    max_right_matches: int
    expanded_left_rows: int
    passed: bool
    rules: list[RuleResult]
    expansions: list[Expansion]
    money: MoneyStats | None = None
    samples_included: bool = False
    unmatched_left_samples: list[list[str]] = field(default_factory=list)
    unmatched_right_samples: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic, JSON-safe result without file paths or source headers."""
        result = asdict(self)
        if not self.samples_included:
            for item in result['expansions']:
                item.pop('key', None)
            result.pop('unmatched_left_samples')
            result.pop('unmatched_right_samples')
        return result
