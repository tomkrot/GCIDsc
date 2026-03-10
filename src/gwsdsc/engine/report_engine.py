"""Report Engine — generates human-readable drift reports from diff results.

Supports:
  * **HTML** — a styled, self-contained HTML report
  * **Markdown** — suitable for Git commit messages, PR descriptions, wiki pages
  * **JSON** — raw structured data

Usage::

    from gwsdsc.engine.diff_engine import DiffEngine
    from gwsdsc.engine.report_engine import ReportEngine

    diff = DiffEngine.compare(baseline, target)
    ReportEngine.generate(diff, format="html", output="report.html")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Template

from gwsdsc.engine.diff_engine import DiffResult, ItemChange, ResourceDiff

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 templates (embedded to keep it single-file)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = Template(
    """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Workspace DSC — Drift Report</title>
<style>
  :root { --bg: #f8f9fa; --card: #fff; --border: #dee2e6; --accent: #1a73e8;
          --added: #1e8e3e; --removed: #d93025; --modified: #f9ab00; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
         color: #202124; line-height: 1.6; padding: 2rem; }
  h1 { color: var(--accent); margin-bottom: .5rem; }
  .meta { color: #5f6368; margin-bottom: 2rem; font-size: .9rem; }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr));
                  gap: 1rem; margin-bottom: 2rem; }
  .summary-card { background: var(--card); border: 1px solid var(--border);
                  border-radius: 8px; padding: 1rem; text-align: center; }
  .summary-card .count { font-size: 2rem; font-weight: 700; }
  .added .count { color: var(--added); }
  .removed .count { color: var(--removed); }
  .modified .count { color: var(--modified); }
  .resource-section { background: var(--card); border: 1px solid var(--border);
                      border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
  .resource-section h2 { font-size: 1.2rem; margin-bottom: .5rem; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
           font-size: .75rem; font-weight: 600; color: #fff; margin-right: .3rem; }
  .badge-added { background: var(--added); }
  .badge-removed { background: var(--removed); }
  .badge-modified { background: var(--modified); }
  table { width: 100%; border-collapse: collapse; margin-top: .75rem; font-size: .85rem; }
  th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--border); }
  th { background: #f1f3f4; font-weight: 600; }
  .detail-json { white-space: pre-wrap; font-family: monospace; font-size: .8rem;
                 max-height: 200px; overflow: auto; background: #f1f3f4;
                 padding: .5rem; border-radius: 4px; margin-top: .25rem; }
  .no-changes { color: #5f6368; font-style: italic; }
  footer { margin-top: 2rem; color: #5f6368; font-size: .8rem; text-align: center; }
</style>
</head>
<body>
<h1>Google Workspace DSC — Drift Report</h1>
<div class="meta">
  Baseline: <strong>{{ diff.baseline_path }}</strong><br>
  Target: <strong>{{ diff.target_path }}</strong><br>
  Baseline exported: {{ diff.baseline_metadata.get('exported_at', 'N/A') }}<br>
  Target exported: {{ diff.target_metadata.get('exported_at', 'N/A') }}
</div>

<div class="summary-grid">
  <div class="summary-card">
    <div class="count">{{ diff.total_changes }}</div>
    <div>Total Changes</div>
  </div>
  <div class="summary-card added">
    <div class="count">{{ total_added }}</div>
    <div>Added</div>
  </div>
  <div class="summary-card removed">
    <div class="count">{{ total_removed }}</div>
    <div>Removed</div>
  </div>
  <div class="summary-card modified">
    <div class="count">{{ total_modified }}</div>
    <div>Modified</div>
  </div>
</div>

{% for name, rd in diff.resources.items() %}
{% if rd.has_changes %}
<div class="resource-section">
  <h2>{{ name }}
    {% if rd.added %}<span class="badge badge-added">+{{ rd.added|length }}</span>{% endif %}
    {% if rd.removed %}<span class="badge badge-removed">-{{ rd.removed|length }}</span>{% endif %}
    {% if rd.modified %}<span class="badge badge-modified">~{{ rd.modified|length }}</span>{% endif %}
  </h2>
  <p>Baseline: {{ rd.baseline_count }} items → Target: {{ rd.target_count }} items</p>

  {% if rd.added %}
  <h3 style="margin-top:1rem; color: var(--added);">Added</h3>
  <table><tr><th>Key</th><th>Preview</th></tr>
  {% for c in rd.added %}
  <tr><td>{{ c.key }}</td><td class="detail-json">{{ c.target_value | tojson(indent=2) if c.target_value else '' }}</td></tr>
  {% endfor %}
  </table>
  {% endif %}

  {% if rd.removed %}
  <h3 style="margin-top:1rem; color: var(--removed);">Removed</h3>
  <table><tr><th>Key</th><th>Preview</th></tr>
  {% for c in rd.removed %}
  <tr><td>{{ c.key }}</td><td class="detail-json">{{ c.baseline_value | tojson(indent=2) if c.baseline_value else '' }}</td></tr>
  {% endfor %}
  </table>
  {% endif %}

  {% if rd.modified %}
  <h3 style="margin-top:1rem; color: var(--modified);">Modified</h3>
  <table><tr><th>Key</th><th>Changes</th></tr>
  {% for c in rd.modified %}
  <tr><td>{{ c.key }}</td><td class="detail-json">{{ c.details | tojson(indent=2) }}</td></tr>
  {% endfor %}
  </table>
  {% endif %}
</div>
{% endif %}
{% endfor %}

{% if not diff.has_changes %}
<p class="no-changes">No configuration drift detected between the two snapshots.</p>
{% endif %}

<footer>Generated by GoogleWorkspaceDsc v0.1.0</footer>
</body>
</html>
"""
)

_MARKDOWN_TEMPLATE = Template(
    """\
# Google Workspace DSC — Drift Report

| | |
|---|---|
| **Baseline** | `{{ diff.baseline_path }}` |
| **Target** | `{{ diff.target_path }}` |
| **Total Changes** | {{ diff.total_changes }} |
| **Added** | {{ total_added }} |
| **Removed** | {{ total_removed }} |
| **Modified** | {{ total_modified }} |

{% for name, rd in diff.resources.items() %}
{% if rd.has_changes %}
## {{ name }} (+{{ rd.added|length }} / -{{ rd.removed|length }} / ~{{ rd.modified|length }})

{% if rd.added %}
### Added
{% for c in rd.added %}
- **{{ c.key }}**
{% endfor %}
{% endif %}

{% if rd.removed %}
### Removed
{% for c in rd.removed %}
- ~~{{ c.key }}~~
{% endfor %}
{% endif %}

{% if rd.modified %}
### Modified
{% for c in rd.modified %}
- **{{ c.key }}**: {{ c.details | tojson }}
{% endfor %}
{% endif %}

{% endif %}
{% endfor %}

{% if not diff.has_changes %}
> No configuration drift detected.
{% endif %}

---
*Generated by GoogleWorkspaceDsc v0.1.0*
"""
)


# ---------------------------------------------------------------------------
# Report Engine
# ---------------------------------------------------------------------------


class ReportEngine:
    """Generate drift reports from a DiffResult."""

    @staticmethod
    def generate(
        diff: DiffResult,
        format: str = "html",
        output: str | Path | None = None,
    ) -> str:
        """Render a report and optionally write it to a file.

        Parameters
        ----------
        diff
            The ``DiffResult`` from ``DiffEngine.compare()``.
        format
            ``"html"``, ``"markdown"`` (or ``"md"``), or ``"json"``.
        output
            File path to write the report to. If ``None``, the rendered
            string is returned without writing.

        Returns
        -------
        str
            The rendered report content.
        """
        totals = _compute_totals(diff)

        if format == "json":
            content = diff.to_json()
        elif format in ("markdown", "md"):
            content = _MARKDOWN_TEMPLATE.render(diff=diff, **totals)
        else:
            content = _HTML_TEMPLATE.render(diff=diff, **totals)

        if output:
            Path(output).write_text(content)
            logger.info("Report written to %s", output)

        return content


def _compute_totals(diff: DiffResult) -> dict[str, int]:
    total_added = sum(len(rd.added) for rd in diff.resources.values())
    total_removed = sum(len(rd.removed) for rd in diff.resources.values())
    total_modified = sum(len(rd.modified) for rd in diff.resources.values())
    return {
        "total_added": total_added,
        "total_removed": total_removed,
        "total_modified": total_modified,
    }
