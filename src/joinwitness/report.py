"""Self-contained, private-by-default HTML reports with no network dependencies."""
from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from .models import AuditResult


def render_report(result: AuditResult) -> str:
    """Render the public result contract, never the underlying source data.

    ``to_dict`` removes key samples unless explicitly enabled. All values still
    pass through Jinja's HTML escaping; the template never marks data as safe.
    Monetary strings are rendered verbatim to preserve exact decimal values.
    """
    environment = Environment(
        loader=PackageLoader('joinwitness', 'templates'),
        autoescape=select_autoescape(enabled_extensions=('html',), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters['count'] = lambda value: format(value, ',d')
    return environment.get_template('report.html').render(audit=result.to_dict())
