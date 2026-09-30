"""Behavior and privacy checks for the portable offline report."""
from dataclasses import replace
from html.parser import HTMLParser

import pytest

from joinwitness.models import AuditResult, Expansion, MoneyStats, RuleResult, SideStats


class ParsedReport(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


@pytest.fixture
def sample_result() -> AuditResult:
    return AuditResult(
        schema_version='1', tool_version='0.1.0', join_type='left',
        expected_relationship='many-to-one', observed_relationship='many-to-many',
        key_columns=1,
        left=SideStats(4, 3, 1, 2, 1, 1, 2, 1),
        right=SideStats(5, 5, 0, 2, 1, 3, 1, 1),
        predicted_rows=8, matched_output_rows=6, expansion_rows=4,
        max_right_matches=3, expanded_left_rows=2, passed=False,
        rules=[RuleResult('relationship', False, 'Right-side keys must be unique.')],
        expansions=[Expansion('Group 1', 2, 3, 6, 4, ['PRIVATE-KEY-123'])],
        money=MoneyStats('0.00', '0.00', '0.00', '0.00', '0.00',
                        '400.00', 2, 4, '0.00', '0.00'),
        unmatched_left_samples=[['PRIVATE-LEFT-KEY']],
        unmatched_right_samples=[['PRIVATE-RIGHT-KEY']],
        notes=['SQL NULL keys never match.'],
    )


def render(result: AuditResult) -> str:
    # Import at call time so missing implementation is a straightforward test failure.
    from importlib import import_module

    import joinwitness
    try:
        module = import_module('joinwitness.report')
    except ModuleNotFoundError:
        pytest.fail('The offline report renderer has not been implemented')
    assert joinwitness is not None
    return module.render_report(result)


def test_report_explains_predicted_rows_and_declared_rule_failure(sample_result):
    html = render(sample_result)
    text = ' '.join(ParsedReport(html).text)
    assert 'Before you join.' in text
    assert 'Needs review' in text
    assert 'Predicted output' in text
    assert '8' in text
    assert 'Input rows' in text
    assert '4' in text
    assert 'many-to-one' in text
    assert 'many-to-many' in text
    assert 'Right-side keys must be unique.' in text
    assert 'Left unmatched rows' in text
    assert 'Right unmatched rows' in text
    assert 'SQL NULL' in text
    assert 'Aggregates' in text
    assert '0.1.0' in text
    assert 'safety score' not in text.lower()


def test_report_uses_privacy_boundary_even_if_dataclass_contains_samples(sample_result):
    html = render(sample_result)
    assert 'PRIVATE-KEY-123' not in html
    assert 'PRIVATE-LEFT-KEY' not in html
    assert 'PRIVATE-RIGHT-KEY' not in html
    assert 'Private by default' in html


def test_report_escapes_every_opted_in_sample_and_note(sample_result):
    payload = '<img src=x onerror=alert(1)><script>alert("x")</script>'
    hostile = replace(
        sample_result, samples_included=True,
        expansions=[Expansion('Group 1', 2, 3, 6, 4, [payload])],
        unmatched_left_samples=[[payload]], unmatched_right_samples=[[payload]],
        notes=[payload], rules=[RuleResult('relationship', False, payload)],
    )
    html = render(hostile)
    parsed = ParsedReport(html)
    assert payload in ''.join(parsed.text)
    assert not any(tag in {'script', 'img'} for tag, _ in parsed.tags)
    assert '&lt;script&gt;' in html
    assert 'Samples included' in html
    assert 'share' in html.lower()


def test_report_shows_exact_money_without_float_rounding_and_cancellation_warning(sample_result):
    huge = '90071992547409931234567890.123456789'
    money = replace(sample_result.money, input_total=huge, output_total=huge,
                    duplicated_signed_amount='0.00', duplicated_absolute_amount='400.00')
    text = ' '.join(ParsedReport(render(replace(sample_result, money=money))).text)
    assert huge in text
    assert 'Signed duplicated amount' in text
    assert 'Absolute duplicated amount' in text
    assert '400.00' in text
    assert 'cancellation can hide duplication' in text.lower()
    assert '$' not in text


def test_report_is_offline_script_free_and_has_restrictive_csp(sample_result):
    html = render(sample_result)
    parsed = ParsedReport(html)
    assert not any(tag in {'script', 'link', 'iframe', 'object', 'embed'} for tag, _ in parsed.tags)
    assert 'https://' not in html and 'http://' not in html
    assert '@import' not in html and 'url(' not in html
    for _, attrs in parsed.tags:
        assert not any(attr.startswith('on') for attr in attrs)
        assert not any(attr in attrs for attr in ['src', 'srcset'])
    policies = [attrs.get('content', '') for tag, attrs in parsed.tags
                if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy']
    assert len(policies) == 1
    assert "default-src 'none'" in policies[0]
    assert "script-src 'none'" in policies[0]
    assert "base-uri 'none'" in policies[0]
    assert "form-action 'none'" in policies[0]


def test_report_has_accessible_document_and_table_structure(sample_result):
    parsed = ParsedReport(render(sample_result))
    assert ('html', {'lang': 'en'}) in parsed.tags
    assert sum(tag == 'h1' for tag, _ in parsed.tags) == 1
    assert any(tag == 'meta' and attrs.get('name') == 'viewport' for tag, attrs in parsed.tags)
    assert any(tag == 'caption' for tag, _ in parsed.tags)
    assert all(attrs.get('scope') in {'col', 'row'} for tag, attrs in parsed.tags if tag == 'th')


def test_passing_result_reports_only_declared_rules_and_handles_empty_inputs(sample_result):
    empty = SideStats(0, 0, 0, 0, 0, 0, 0, 0)
    result = replace(sample_result, left=empty, right=empty, predicted_rows=0,
                     matched_output_rows=0, expansion_rows=0, max_right_matches=0,
                     expanded_left_rows=0, passed=True,
                     observed_relationship='one-to-one', money=None, expansions=[],
                     rules=[RuleResult('relationship', True, 'Declared relationship passes.')])
    text = ' '.join(ParsedReport(render(result)).text)
    assert 'All declared rules pass' in text
    assert 'No expanding key groups' in text
    assert 'No amount column selected' in text
    assert 'nan' not in text.lower()
    assert 'infinity' not in text.lower()
