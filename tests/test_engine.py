"""Contract and edge-case tests for exact, private CSV join preflights."""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from joinwitness.models import AuditConfig, InputError


def write_csv(path: Path, rows: list[list[str]], *, delimiter: str = ',') -> Path:
    with path.open('w', encoding='utf-8', newline='') as stream:
        csv.writer(stream, delimiter=delimiter).writerows(rows)
    return path


def make_config(tmp_path: Path, left: list[list[str]], right: list[list[str]], **options: object) -> AuditConfig:
    return AuditConfig(
        left=write_csv(tmp_path / 'SECRET-left.csv', left),
        right=write_csv(tmp_path / 'SECRET-right.csv', right),
        left_keys=('id',), right_keys=('id',), **options,
    )


def run(config: AuditConfig):
    from joinwitness.engine import audit
    return audit(config)


def test_counts_output_without_materializing_cartesian_product(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id']] + [['x']] * 2_000, [['id']] + [['x']] * 3_000)
    result = run(config)
    assert result.predicted_rows == 6_000_000
    assert result.expansion_rows == 5_998_000
    assert result.expanded_left_rows == 2_000
    assert result.max_right_matches == 3_000
    assert result.left.duplicate_keys == result.right.duplicate_keys == 1
    assert result.left.duplicate_excess_rows == 1_999
    assert result.observed_relationship == 'many-to-many'
    assert not result.passed


@pytest.mark.parametrize(('join_type', 'expected'), [('left', 6), ('inner', 4)])
def test_nulls_do_not_match_and_unmatched_rows_count_on_both_sides(tmp_path: Path, join_type: str, expected: int) -> None:
    config = make_config(tmp_path, [['id'], ['a'], ['a'], [''], ['left']],
                         [['id'], ['a'], ['a'], [''], ['right']], join_type=join_type,
                         relationship='many-to-many', fail_on_unmatched=True)
    result = run(config)
    assert result.predicted_rows == expected
    assert result.matched_output_rows == 4
    assert result.left.null_key_rows == result.right.null_key_rows == 1
    assert result.left.unmatched_rows == result.right.unmatched_rows == 2
    assert result.left.unmatched_keys == result.right.unmatched_keys == 1
    assert result.left.matchable_rows == 3
    assert result.left.distinct_matchable_keys == 2
    assert not result.passed
    assert {r.code: r.passed for r in result.rules} == {'relationship': True, 'unmatched': False}


def test_composite_keys_are_tuples_and_any_null_component_is_unmatchable(tmp_path: Path) -> None:
    left = write_csv(tmp_path / 'left', [['a', 'b'], ['x|y', 'z'], ['x', 'y|z'], ['', 'z']])
    right = write_csv(tmp_path / 'right', [['c', 'd'], ['x', 'y|z'], ['', 'z']])
    result = run(AuditConfig(left, right, ('a', 'b'), ('c', 'd'), join_type='inner'))
    assert result.predicted_rows == 1
    assert result.key_columns == 2
    assert result.left.unmatched_rows == 2
    assert result.left.unmatched_keys == 1


def test_keys_preserve_unicode_leading_zero_and_whitespace(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['01'], [' 1'], ['1 '], ['é'], ['e\u0301']],
                         [['id'], ['1'], ['é']])
    result = run(replace(config, join_type='inner'))
    assert result.predicted_rows == 1
    assert result.left.unmatched_rows == 4


def test_null_literals_are_exact_and_can_be_disabled(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['NULL'], ['null'], ['']],
                         [['id'], ['NULL'], ['null'], ['']], null_values=('NULL',))
    assert run(config).matched_output_rows == 2
    assert run(replace(config, null_values=())).matched_output_rows == 3


@pytest.mark.parametrize('relationship', ['one-to-one', 'one-to-many'])
def test_left_uniqueness_is_checked_even_for_unmatched_keys(tmp_path: Path, relationship: str) -> None:
    config = make_config(tmp_path, [['id'], ['unmatched'], ['unmatched']], [['id'], ['other']],
                         relationship=relationship)
    assert not run(config).passed


@pytest.mark.parametrize('relationship', ['one-to-one', 'many-to-one'])
def test_right_uniqueness_is_checked_even_for_unmatched_keys(tmp_path: Path, relationship: str) -> None:
    config = make_config(tmp_path, [['id'], ['other']], [['id'], ['unmatched'], ['unmatched']],
                         relationship=relationship)
    assert not run(config).passed


def test_duplicate_nulls_do_not_violate_uniqueness(tmp_path: Path) -> None:
    result = run(make_config(tmp_path, [['id'], [''], ['']], [['id'], [''], ['']], relationship='one-to-one'))
    assert result.passed
    assert result.observed_relationship == 'one-to-one'
    assert result.left.duplicate_keys == 0
    assert result.left.unmatched_rows == 2


def test_rule_thresholds_are_inclusive_and_unmatched_checks_right_input(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['a']], [['id'], ['a'], ['a'], ['right']],
                         relationship='many-to-many', max_output_rows=2, fail_on_expansion=True,
                         fail_on_unmatched=True)
    assert {r.code: r.passed for r in run(config).rules} == {
        'relationship': True, 'max_output_rows': True, 'unmatched': False, 'expansion': False,
    }
    assert not next(r for r in run(replace(config, max_output_rows=1)).rules if r.code == 'max_output_rows').passed


def test_header_only_inputs_are_valid_empty_tables(tmp_path: Path) -> None:
    result = run(make_config(tmp_path, [['id', 'value']], [['id']], amount_column='value',
                             max_output_rows=0, fail_on_unmatched=True, fail_on_expansion=True))
    assert result.passed
    assert result.predicted_rows == result.max_right_matches == 0
    assert result.money is not None
    assert result.money.input_total == result.money.output_total == '0'


def test_exact_money_preserves_signed_zero_sum_duplication(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id', 'money'], ['a', '10.10'], ['a', '-10.10'], ['b', '7.25'], ['', '2.5']],
                         [['id'], ['a'], ['a'], ['a']], relationship='many-to-many', amount_column='money')
    result = run(config)
    money = result.money
    assert money is not None
    assert money.input_total == '9.75'
    assert money.matched_input_total == '0'
    assert money.unmatched_input_total == '9.75'
    assert money.output_total == '9.75'
    assert money.duplicated_signed_amount == '0'
    assert money.duplicated_absolute_amount == '40.4'
    assert money.duplicated_left_rows == 2
    assert money.extra_copies == 4
    assert money.dropped_amount == money.net_change == '0'
    inner = run(replace(config, join_type='inner')).money
    assert inner is not None
    assert inner.output_total == '0'
    assert inner.dropped_amount == '9.75'
    assert inner.net_change == '-9.75'


def test_money_is_exact_independently_of_decimal_context(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id', 'money'], ['a', '12345678901234567890.123456789012345678'], ['a', '0.000000000000000001']],
                         [['id'], ['a'], ['a']], amount_column='money', relationship='many-to-many')
    with localcontext() as context:
        context.prec = 3
        money = run(config).money
    assert money is not None
    assert money.input_total == '12345678901234567890.123456789012345679'
    assert money.output_total == '24691357802469135780.246913578024691358'


@pytest.mark.parametrize('amount', ['', ' ', ' 1', '1 ', 'NaN', 'Inf', '-Infinity', '1e2', '1,000', '1_000',
                                    '１２', '0.0000000000000000001', '9' * 39])
def test_invalid_amount_rejected_on_null_and_unmatched_rows(tmp_path: Path, amount: str) -> None:
    config = make_config(tmp_path, [['id', 'money'], ['', amount]], [['id'], ['other']], amount_column='money')
    with pytest.raises(InputError, match='amount|monetary'):
        run(config)


@pytest.mark.parametrize('amount', ['+0.00', '-0', '.5', '1.', '+12.50', '-.5'])
def test_valid_plain_decimal_forms(tmp_path: Path, amount: str) -> None:
    config = make_config(tmp_path, [['id', 'money'], ['a', amount]], [['id'], ['a']], amount_column='money')
    money = run(config).money
    assert money is not None
    assert Decimal(money.input_total) == Decimal(amount)


def test_bom_delimiter_quoted_newlines_and_escaped_quotes(tmp_path: Path) -> None:
    left = tmp_path / 'left.csv'
    right = tmp_path / 'right.csv'
    content = 'id;value\r\n"hello\r\nworld";"a""b"\r\n'
    left.write_bytes(b'\xef\xbb\xbf' + content.encode())
    right.write_bytes(content.encode())
    result = run(AuditConfig(left, right, ('id',), ('id',), delimiter=';'))
    assert result.predicted_rows == 1
    assert result.left.rows == 1


@pytest.mark.parametrize('content', [
    b'', b'id,id\na,b\n', b'id,value\na\n', b'id\na,b\n', b'id\n"unterminated\n',
    b'id\na"b\n', b'id\n"a"oops\n', b'id\n\xff\n', b'id\na\x00b\n', b'id\n\n',
])
def test_invalid_csv_is_rejected(tmp_path: Path, content: bytes) -> None:
    config = make_config(tmp_path, [['id']], [['id']])
    config.left.write_bytes(content)
    with pytest.raises(InputError):
        run(config)


def test_field_bound_is_checked_including_multiline_fields(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['x' * 131_072]], [['id']])
    assert run(config).left.rows == 1
    config.left.write_text('id\n"' + 'x' * 131_070 + '\nabc"\n', encoding='utf-8')
    with pytest.raises(InputError, match='field|limit|long'):
        run(config)


@pytest.mark.parametrize('updates', [
    {'left_keys': ()}, {'right_keys': ('id', 'other')}, {'left_keys': ('id', 'id'), 'right_keys': ('id', 'id')},
    {'left_keys': ('missing',)}, {'amount_column': 'missing'}, {'delimiter': ''}, {'delimiter': 'ab'},
    {'delimiter': '\n'}, {'delimiter': '"'}, {'sample_limit': -1}, {'max_output_rows': -1},
    {'join_type': 'outer'}, {'relationship': 'invalid'},
])
def test_bad_configuration_is_input_error(tmp_path: Path, updates: dict[str, object]) -> None:
    config = make_config(tmp_path, [['id']], [['id']])
    with pytest.raises(InputError):
        run(replace(config, **updates))


def test_missing_and_directory_inputs_are_input_errors(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id']], [['id']])
    for path in [tmp_path / 'missing.csv', tmp_path]:
        with pytest.raises(InputError):
            run(replace(config, left=path))


def test_default_serialization_is_private_and_deterministic(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['SECRET-key'], ['SECRET-unmatched']],
                         [['id'], ['SECRET-key'], ['SECRET-key'], ['SECRET-right']], relationship='many-to-many')
    result = run(config)
    serialized = json.dumps(result.to_dict(), sort_keys=True)
    assert 'SECRET' not in serialized
    assert 'unmatched_left_samples' not in result.to_dict()
    assert all('key' not in group for group in result.to_dict()['expansions'])
    assert result.to_dict() == run(config).to_dict()
    assert result.expansions[0].group == 'Group 1'


def test_expansions_are_stable_top_ten_and_sample_budget_is_global(tmp_path: Path) -> None:
    left = [['id']] + [[str(index)] for index in reversed(range(12))] + [['z-left']]
    right = [['id']] + [[str(index)] for index in range(12) for _ in range(index + 2)] + [['z-right']]
    config = make_config(tmp_path, left, right, relationship='many-to-many', sample_limit=11)
    result = run(config)
    assert len(result.expansions) == 10
    assert [group.key for group in result.expansions] == [[str(index)] for index in range(11, 1, -1)]
    assert result.unmatched_left_samples == [['z-left']]
    assert result.unmatched_right_samples == []
    assert result.samples_included
    total_samples = sum(group.key is not None for group in result.expansions) + len(result.unmatched_left_samples) + len(result.unmatched_right_samples)
    assert total_samples == 11


def test_sample_budget_less_than_expansion_groups_does_not_leak_more_keys(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['b'], ['a']], [['id'], ['b'], ['b'], ['a'], ['a']],
                         relationship='many-to-many', sample_limit=1)
    result = run(config)
    assert result.expansions[0].key == ['a']
    assert result.expansions[1].key is None
    assert result.expansions[0].extra_left_copies == 1


def test_inputs_remain_unchanged(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id'], ['a']], [['id'], ['a']])
    before = config.left.read_bytes(), config.right.read_bytes()
    run(config)
    assert before == (config.left.read_bytes(), config.right.read_bytes())


@pytest.mark.parametrize('updates', [
    {'sample_limit': 101}, {'left_keys': ('',)}, {'right_keys': ('',)}, {'amount_column': ''},
    {'fail_on_unmatched': 1}, {'fail_on_unmatched': 'false'}, {'fail_on_expansion': 0},
])
def test_direct_api_enforces_cli_configuration_bounds(tmp_path: Path, updates: dict[str, object]) -> None:
    config = make_config(tmp_path, [['id']], [['id']])
    with pytest.raises(InputError):
        run(replace(config, **updates))


def test_empty_header_name_is_invalid_even_when_unselected(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id', ''], ['a', 'value']], [['id'], ['a']])
    with pytest.raises(InputError, match='header'):
        run(config)


def test_whitespace_header_name_remains_an_exact_distinct_name(tmp_path: Path) -> None:
    config = make_config(tmp_path, [['id', ' '], ['a', 'b']], [['id', ' '], ['a', 'b']])
    assert run(replace(config, left_keys=(' ',), right_keys=(' ',))).predicted_rows == 1
