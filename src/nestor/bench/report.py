"""Reports of one or several runs: an aligned table for the terminal, a self-contained HTML page.

The page loads nothing from the network: styles and charts (SVG) are inline, so it opens anywhere and can
be attached to a pull request as it is.
"""

import html
import json
from collections.abc import Callable, Sequence

from nestor.bench.results import Run
from nestor.bench.types import Better, Metric, Unit
from nestor.core.i18n import Message

type Render = Callable[[Message], str]

BEST = "*"


def value_text(value: float | None, unit: Unit) -> str:
    if value is None:
        return "-"
    match unit:
        case Unit.RATIO:
            return f"{value:.3f}"
        case Unit.DURATION:
            return f"{value * 1000:.0f} ms" if value < 10 else f"{value:.1f} s"
        case Unit.COST:
            return f"{value:.4f}"
        case _:  # Unit.COUNT
            return f"{value:.0f}" if float(value).is_integer() else f"{value:.2f}"


def _rows(runs: Sequence[Run]) -> list[tuple[Metric, list[Metric | None]]]:
    """Each metric, in the order of the first run that has it, with every run's value of it."""
    order: dict[str, Metric] = {}
    for run in runs:
        for metric in run.summary.metrics:
            order.setdefault(metric.id, metric)
    by_run = [{m.id: m for m in run.summary.metrics} for run in runs]
    return [(first, [values.get(id) for values in by_run]) for id, first in order.items()]


def _best(metric: Metric, values: Sequence[Metric | None]) -> set[int]:
    """The runs with the best value, when there is a direction, a choice, and not a tie of all."""
    known = {i: m.value for i, m in enumerate(values) if m is not None and m.value is not None}
    if metric.better is Better.NEITHER or len(known) < 2 or len(set(known.values())) == 1:
        return set()
    pick = max if metric.better is Better.HIGHER else min
    target = pick(known.values())
    return {i for i, v in known.items() if v == target}


def _header(runs: Sequence[Run], render: Render) -> str:
    first = runs[0]
    return render(
        Message.of(
            "bench-table-header",
            suite=first.suite,
            dataset=first.dataset.sha256[:12],
            version=first.dataset.version,
            cases=first.dataset.cases,
            repeat=first.repeat,
            seed=first.seed,
        )
    )


def table(runs: Sequence[Run], render: Render) -> str:
    """The metrics of `runs` side by side, the best of each row marked; then each run's models and folder."""
    head = [render(Message.of("bench-column-metric")), *(r.variant for r in runs)]
    body = []
    for metric, values in _rows(runs):
        best = _best(metric, values)
        cells = [
            value_text(m.value if m else None, metric.unit) + (BEST if i in best else "") for i, m in enumerate(values)
        ]
        body.append([render(Message.of(metric.label)), *cells])
    widths = [max(len(row[i]) for row in [head, *body]) for i in range(len(head))]

    def line(row: list[str]) -> str:
        return "  ".join([row[0].ljust(widths[0]), *(c.rjust(w) for c, w in zip(row[1:], widths[1:], strict=True))])

    lines = [_header(runs, render), "", line(head), "  ".join("-" * w for w in widths), *map(line, body), ""]
    if any(_best(m, v) for m, v in _rows(runs)):
        lines.append(render(Message.of("bench-table-best", mark=BEST)))
    if any(r.dataset.sha256 != runs[0].dataset.sha256 for r in runs):
        lines.append(render(Message.of("bench-different-datasets")))
    for run in runs:
        served = ", ".join(run.served_models) or "-"
        replayed = "yes" if run.replay else "no"
        lines.append(render(Message.of("bench-table-run", variant=run.variant, served=served, replayed=replayed)))
    return "\n".join(lines)


def findings_text(run: Run, render: Render) -> str:
    groups: dict[str, list[str]] = {}
    for finding in run.summary.findings:
        groups.setdefault(finding.group, []).append(f"  {render(finding.detail)}")
    return "\n\n".join(f"{render(Message.of(group))}\n" + "\n".join(lines) for group, lines in groups.items())


def page(runs: Sequence[Run], render: Render, *, lang: str = "en") -> str:
    """The HTML report of one run, or the comparison of several."""
    esc = html.escape

    def words(id: str) -> str:
        return esc(render(Message.of(id)))

    def cell(i: int, metric: Metric, values: Sequence[Metric | None]) -> str:
        value = values[i]
        text = esc(value_text(value.value if value else None, metric.unit))
        return f"<td class='best'>{text}</td>" if i in _best(metric, values) else f"<td>{text}</td>"

    rows = _rows(runs)
    metrics = "".join(
        f"<tr><th scope='row'>{words(m.label)}</th>{''.join(cell(i, m, values) for i in range(len(runs)))}</tr>"
        for m, values in rows
    )
    variants = "".join(f"<th scope='col'>{esc(r.variant)}</th>" for r in runs)
    columns = "".join(
        f"<th scope='col'>{words(f'bench-column-{c}')}</th>"
        for c in ("variant", "served", "config", "dataset", "repeat", "version", "started")
    )
    described = "".join(_described(run, words("bench-report-replayed")) for run in runs)
    charts = "".join(_chart(words(metric.label), metric, values, runs) for metric, values in rows)
    findings = "".join(_findings(run, render) for run in runs) or f"<p>{words('bench-report-no-findings')}</p>"
    title = f"{words('bench-report-title')} · {esc(runs[0].suite)}"
    return f"""<!doctype html>
<html lang="{esc(lang)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_STYLE}</style></head>
<body><main>
<h1>{title}</h1>
<p class="meta">{esc(_header(runs, render))}</p>
<h2>{words("bench-report-metrics")}</h2>
<div class="scroll"><table><thead><tr><th scope="col">{words("bench-column-metric")}</th>{variants}</tr></thead>
<tbody>{metrics}</tbody></table></div>
<p class="meta">{words("bench-report-best")}</p>
<h2>{words("bench-report-charts")}</h2>
<div class="charts">{charts}</div>
<h2>{words("bench-report-runs")}</h2>
<div class="scroll"><table><thead><tr>{columns}</tr></thead>
<tbody>{described}</tbody></table></div>
<h2>{words("bench-report-findings")}</h2>
{findings}
</main></body></html>
"""


def _described(run: Run, replayed: str) -> str:
    esc = html.escape
    config = esc(json.dumps(run.config, ensure_ascii=False, indent=1))
    repeat = f"{run.repeat} / {run.seed}" + (f" / {replayed}" if run.replay else "")
    cells = (
        esc(", ".join(run.served_models) or "-"),
        f"<pre>{config}</pre>",
        f"{esc(run.dataset.sha256[:12])} (v{run.dataset.version}, {run.dataset.cases})",
        repeat,
        f"{esc(run.nestor)}<br><code>{esc((run.commit or '-')[:19])}</code>",
        esc(run.started_at.isoformat(timespec="seconds")),
    )
    return f"<tr><th scope='row'>{esc(run.variant)}</th>{''.join(f'<td>{c}</td>' for c in cells)}</tr>"


def _chart(label: str, metric: Metric, values: Sequence[Metric | None], runs: Sequence[Run]) -> str:
    """Horizontal bars, one per run, the best ones in the accent colour; ratios on a 0 to 1 scale."""
    known = [m.value if m is not None else None for m in values]
    if all(v is None for v in known):
        return ""
    top = 1.0 if metric.unit is Unit.RATIO else max(v for v in known if v is not None) or 1.0
    best = _best(metric, values)
    bar, gap, left, width = 18, 6, 140, 420
    bars = []
    for i, (run, value) in enumerate(zip(runs, known, strict=True)):
        y = i * (bar + gap)
        length = 0 if value is None else (width - left - 70) * value / top
        kind = "bar best" if i in best else "bar"
        text = html.escape(value_text(value, metric.unit))
        bars.append(
            f"<text x='0' y='{y + 13}' class='name'>{html.escape(run.variant[:22])}</text>"
            f"<rect x='{left}' y='{y}' width='{length:.1f}' height='{bar}' rx='3' class='{kind}'/>"
            f"<text x='{left + length + 6:.1f}' y='{y + 13}' class='value'>{text}</text>"
        )
    height = len(runs) * (bar + gap)
    return (
        f"<figure><figcaption>{label}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{label}'>{''.join(bars)}</svg></figure>"
    )


def _findings(run: Run, render: Render) -> str:
    groups: dict[str, list[str]] = {}
    for finding in run.summary.findings:
        groups.setdefault(finding.group, []).append(f"<li>{html.escape(render(finding.detail))}</li>")
    if not groups:
        return ""
    inner = "".join(
        f"<details><summary>{html.escape(render(Message.of(group)))} ({len(items)})</summary>"
        f"<ul>{''.join(items)}</ul></details>"
        for group, items in groups.items()
    )
    return f"<section><h3>{html.escape(run.variant)}</h3>{inner}</section>"


_STYLE = """
:root{--bg:#fbfaf7;--fg:#1d1b18;--muted:#6b665e;--line:#e4e0d8;--bar:#9a958c;--best:#c2410c;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8e1;--muted:#a19b91;--line:#34312c;--bar:#6f6a62;
--best:#f97316;--card:#1e1d1a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:0 0 4px}
h2{font-size:1.15rem;margin:32px 0 12px}h3{font-size:1rem;margin:16px 0 8px}.meta{color:var(--muted);margin:4px 0}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card)}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top;white-space:nowrap}
th[scope=row],thead th:first-child{text-align:left}td pre{margin:0;text-align:left;font-size:12px;white-space:pre}
td.best{color:var(--best);font-weight:600}
.charts{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:16px}
figure{margin:0;padding:12px;background:var(--card);border:1px solid var(--line);border-radius:8px}
figcaption{font-weight:600;margin-bottom:8px}svg{width:100%;height:auto;font:12px system-ui,sans-serif}
svg .name,svg .value{fill:var(--fg)}svg .bar{fill:var(--bar)}svg .bar.best{fill:var(--best)}
details{margin:6px 0}summary{cursor:pointer}ul{margin:6px 0 0;padding-left:20px}li{margin:2px 0}
"""
