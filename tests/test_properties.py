"""Small reference joins validate aggregate results without shared algorithms."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from joinwitness.models import AuditConfig

KEY = st.sampled_from(['', 'a', 'b', '01', '1', ' x', 'é', 'a|b', '"', '\n'])
ROWS = st.lists(st.tuples(KEY, KEY, st.integers(-10_000, 10_000)), max_size=8)


@given(left_rows=ROWS, right_rows=ROWS, join_type=st.sampled_from(['left', 'inner']),
       relationship=st.sampled_from(['one-to-one', 'one-to-many', 'many-to-one', 'many-to-many']))
@settings(max_examples=160, deadline=None)
def test_aggregate_engine_matches_small_materialized_reference(left_rows, right_rows, join_type, relationship) -> None:
    from joinwitness.engine import audit

    with TemporaryDirectory() as directory:
        paths = [Path(directory) / 'left.csv', Path(directory) / 'right.csv']
        for path, rows in zip(paths, [left_rows, right_rows], strict=True):
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['a', 'b', 'money'])
                writer.writerows((a, b, f'{amount / 100:.2f}') for a, b, amount in rows)
        result = audit(AuditConfig(*paths, ('a', 'b'), ('a', 'b'), relationship=relationship,
                                   join_type=join_type, amount_column='money'))

    def matching(left, right):
        return all(component != '' for component in left[:2] + right[:2]) and left[:2] == right[:2]

    matched_pairs = [(left, right) for left in left_rows for right in right_rows if matching(left, right)]
    left_unmatched = [left for left in left_rows if not any(matching(left, right) for right in right_rows)]
    right_unmatched = [right for right in right_rows if not any(matching(left, right) for left in left_rows)]
    output = [(left, right) for left, right in matched_pairs]
    if join_type == 'left':
        output.extend((left, None) for left in left_unmatched)
    copies = [sum(matching(left, right) for right in right_rows) for left in left_rows]
    assert result.predicted_rows == len(output)
    assert result.matched_output_rows == len(matched_pairs)
    assert result.left.unmatched_rows == len(left_unmatched)
    assert result.right.unmatched_rows == len(right_unmatched)
    assert result.max_right_matches == max(copies, default=0)
    assert result.expansion_rows == sum(max(count - 1, 0) for count in copies)
    assert result.expanded_left_rows == sum(count > 1 for count in copies)
    money = result.money
    assert money is not None
    assert Decimal(money.input_total) * 100 == sum(left[2] for left in left_rows)
    assert Decimal(money.output_total) * 100 == sum(left[2] for left, _ in output)
    assert Decimal(money.matched_input_total) * 100 == sum(left[2] for left, count in zip(left_rows, copies, strict=True) if count)
    assert Decimal(money.duplicated_signed_amount) * 100 == sum(left[2] * max(count - 1, 0) for left, count in zip(left_rows, copies, strict=True))
    assert Decimal(money.duplicated_absolute_amount) * 100 == sum(abs(left[2]) * max(count - 1, 0) for left, count in zip(left_rows, copies, strict=True))
    assert money.duplicated_left_rows == result.expanded_left_rows
    assert money.extra_copies == result.expansion_rows
    assert Decimal(money.dropped_amount) * 100 == (sum(left[2] for left in left_unmatched) if join_type == 'inner' else 0)
    assert Decimal(money.net_change) == Decimal(money.output_total) - Decimal(money.input_total)

    unique = []
    for rows in [left_rows, right_rows]:
        keys = [row[:2] for row in rows if '' not in row[:2]]
        unique.append(len(keys) == len(set(keys)))
    expected_pass = ((relationship not in ('one-to-one', 'one-to-many') or unique[0]) and
                     (relationship not in ('one-to-one', 'many-to-one') or unique[1]))
    assert result.passed == expected_pass
