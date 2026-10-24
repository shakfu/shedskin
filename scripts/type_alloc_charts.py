#!/usr/bin/env python3
"""Generate the SVG charts for docs/dev/type-alloc.md (stdlib only).

Horizontal bar charts, one or more series per category, with a
prefers-color-scheme dark palette inside each SVG. At most three series:
categorical slots 1-3 stay distinguishable for color-blind readers.

The JSON file maps each SVG path, relative to the JSON file, to a chart spec.

usage: python3 scripts/type_alloc_charts.py docs/dev/type-alloc-charts.json
"""

import json
import os
import sys
from html import escape

STYLE = """
<style>
  .s { fill: #fcfcfb; } .t1 { fill: #0b0b0b; } .t2 { fill: #52514e; }
  .g { stroke: #e4e3df; } .ax { stroke: #a3a29c; }
  .c0 { fill: #2a78d6; } .c1 { fill: #eb6834; } .c2 { fill: #1baf7a; }
  .gap { stroke: #fcfcfb; }
  @media (prefers-color-scheme: dark) {
    .s { fill: #1a1a19; } .t1 { fill: #f0efec; } .t2 { fill: #c3c2b7; }
    .g { stroke: #2e2e2c; } .ax { stroke: #6b6a65; }
    .c0 { fill: #3987e5; } .c1 { fill: #d95926; } .c2 { fill: #199e70; }
    .gap { stroke: #1a1a19; }
  }
  text { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
</style>
"""


def nice_max(v):
    for e in range(-3, 8):
        for m in (1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8):
            top = m * 10**e
            if top >= v:
                return top
    return v


def bar(x, y, w, h, cls):
    """Bar anchored at x, 4px rounded at the data end only."""
    r = min(4, w / 2, h / 2)
    if w <= 0:
        return ""
    return (
        f'<path class="{cls}" d="M{x:.1f},{y:.1f} h{w - r:.1f} '
        f"a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} a{r},{r} 0 0 1 -{r},{r} "
        f'h-{w - r:.1f} z"/>'
    )


def chart(spec):
    title, unit = spec["title"], spec["unit"]
    cats, series = spec["categories"], spec["series"]  # series: [[name, [values]]]
    fmt = spec.get("fmt", "{:g}")
    n = len(series)
    bh, gap, group_gap = 14, 2, 12
    label_w, right = spec.get("label_w", 120), 70
    width = 680
    plot_w = width - label_w - right
    top = 48 + (22 if n > 1 else 0)
    group_h = n * bh + (n - 1) * gap
    height = top + len(cats) * (group_h + group_gap) + 34
    vmax = nice_max(max(max(v) for _, v in series))
    sx = plot_w / vmax
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        ),
        STYLE,
        f'<rect class="s" width="{width}" height="{height}" rx="6"/>',
        f'<text class="t1" x="16" y="26" font-size="15" font-weight="600">{escape(title)}</text>',
    ]
    if n > 1:  # legend, one row above the plot
        lx = label_w
        for i, (name, _) in enumerate(series):
            out.append(
                f'<rect class="c{i}" x="{lx}" y="40" width="12" height="12" rx="3"/>'
            )
            out.append(
                f'<text class="t2" x="{lx + 18}" y="50" font-size="12">{escape(name)}</text>'
            )
            lx += 30 + 7 * len(name)
    plot_bottom = height - 34
    for k in range(5):  # recessive grid and tick labels
        v = vmax * k / 4
        x = label_w + v * sx
        out.append(
            f'<line class="g" x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{plot_bottom}" stroke-width="1"/>'
        )
        out.append(
            f'<text class="t2" x="{x:.1f}" y="{plot_bottom + 16}" font-size="11" '
            f'text-anchor="middle">{v:g}</text>'
        )
    out.append(
        f'<text class="t2" x="{label_w + plot_w}" y="{plot_bottom + 30}" font-size="11" '
        f'text-anchor="end">{escape(unit)}</text>'
    )
    y = top
    for ci, cat in enumerate(cats):
        out.append(
            f'<text class="t1" x="{label_w - 8}" y="{y + group_h / 2 + 4:.1f}" font-size="12" '
            f'text-anchor="end">{escape(cat)}</text>'
        )
        for si, (name, vals) in enumerate(series):
            v = vals[ci]
            yy = y + si * (bh + gap)
            out.append(bar(label_w, yy, v * sx, bh, f"c{si}"))
            out.append(
                f'<text class="t2" x="{label_w + v * sx + 6:.1f}" y="{yy + bh - 3}" '
                f'font-size="11">{fmt.format(v)}</text>'
            )
        y += group_h + group_gap
    out.append(
        f'<line class="ax" x1="{label_w}" y1="{top - 6}" x2="{label_w}" y2="{plot_bottom}" stroke-width="1"/>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        specs = json.load(f)
    for name, spec in specs.items():
        assert len(spec["series"]) <= 3, name
        path = os.path.join(os.path.dirname(sys.argv[1]), name)
        with open(path, "w") as f:
            f.write(chart(spec))
        print("wrote", path)
