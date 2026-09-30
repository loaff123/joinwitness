"""Independent Decimal reference for mixed-scale signed monetary expansion."""
import csv
from decimal import Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from joinwitness.engine import audit
from joinwitness.models import AuditConfig


@st.composite
def decimal_text(draw):
    coefficient = draw(st.integers(-(10**20), 10**20))
    scale = draw(st.integers(0, 18))
    digits = str(abs(coefficient)).rjust(scale + 1, '0')
    value = digits if not scale else digits[:-scale] + '.' + digits[-scale:]
    return ('-' if coefficient < 0 else '') + value


@given(values=st.lists(decimal_text(), min_size=1, max_size=8), repeats=st.integers(1, 7))
@settings(max_examples=80, deadline=None)
def test_mixed_scale_money_matches_high_precision_reference(values, repeats):
    with TemporaryDirectory() as directory:
        left, right = Path(directory) / 'l.csv', Path(directory) / 'r.csv'
        with left.open('w', encoding='utf-8', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['id', 'amount'])
            writer.writerows([['same', value] for value in values])
        right.write_text('id\n' + 'same\n' * repeats, encoding='utf-8')
        result = audit(AuditConfig(left, right, ('id',), ('id',),
                                  relationship='many-to-many', amount_column='amount'))
    assert result.money is not None
    with localcontext() as context:
        context.prec = 120
        expected = sum(map(Decimal, values))
        absolute = sum(abs(Decimal(value)) for value in values)
        assert Decimal(result.money.input_total) == expected
        assert Decimal(result.money.output_total) == expected * repeats
        assert Decimal(result.money.duplicated_signed_amount) == expected * (repeats - 1)
        assert Decimal(result.money.duplicated_absolute_amount) == absolute * (repeats - 1)
