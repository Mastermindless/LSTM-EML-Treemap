"""End-to-end pipeline driver.

Runs LSTM-EML discovery, validates, renders Mermaid plots grouped by which
component of the value carries π (real / imaginary / Pythagoras), and
emits two artifacts:

    output/validated_trees.md      — one section per tree with mermaid block
    output/validated_trees.html    — same content rendered with mermaid.js

Run:
    python -m pipeline.build_report --n 20 --train-steps 800
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src_tree_search"))

from pipeline.discover_pi import Discovered, discover  # noqa: E402
from pipeline.mermaid_render import render_expression, render_mermaid  # noqa: E402
from pipeline.tree_validation import (  # noqa: E402
    evaluate_high_precision_digits,
)


GROUP_ORDER = ["real", "imaginary", "pythagoras"]
GROUP_TITLE = {
    "real":       "I. π via the **real** part",
    "imaginary":  "II. π via the **imaginary** part   (typically `ln(−1) = i·π`)",
    "pythagoras": "III. π via the **Pythagorean magnitude** `|v| = √(Re² + Im²)`",
}
GROUP_DESCRIPTION = {
    "real": (
        "Trees whose evaluated value has its real component matching π. "
        "Within the EML-only operator family this is structurally the "
        "hardest path because EML never multiplies — the only way to "
        "*move* a `−i·π` from `ln(−1)` onto the real line is by re-feeding "
        "it through `−ln`."
    ),
    "imaginary": (
        "Trees whose imaginary part — or its absolute value — matches π. "
        "These are the bread-and-butter EML pi identities: `ln(−1) = i·π` "
        "is the lone vocabulary path that exposes π to the search."
    ),
    "pythagoras": (
        "Trees whose Pythagorean magnitude `|v| = √(Re² + Im²)` matches π. "
        "These tend to be the deepest finds: the search has shaped both "
        "the real and imaginary parts so their RSS lands on π."
    ),
}


def group_results(found: list[Discovered]) -> dict[str, list[Discovered]]:
    by_group: dict[str, list[Discovered]] = defaultdict(list)
    for d in found:
        by_group[d.hit.group].append(d)
    for g in by_group:
        # rank within a group: more digits → smaller error → smaller tree
        by_group[g].sort(
            key=lambda d: (-d.hit.digits, d.hit.abs_err, d.hit.size, d.hit.depth)
        )
    return by_group


def write_markdown(found: list[Discovered], out_path: Path, hp_dps: int) -> None:
    lines: list[str] = []
    lines.append("# Validated π Trees — LSTM-EML Search Gallery")
    lines.append("")
    lines.append(
        "Every tree below is a discovery in the EML-only operator family "
        f"`EML(x, y) = exp(x) − ln(y)`. Each one was sampled (or hand-derived "
        "as a positive-control seed) and validated by re-evaluating the tree "
        f"in `mpmath` at {hp_dps} decimal digits. The reported digit count is the "
        "leading-digit agreement of the named channel with π."
    )
    lines.append("")
    lines.append(
        "Visualization convention (per the project spec): the **left/exp child** of every "
        "`EML` node is drawn *upward* (the exponential grows like a tree trunk), and the "
        "**right/ln child** is drawn *to the side* (the logarithm branches out). Constant "
        "leaves are rendered as labelled blocks, and the leaf `1` is drawn as a green "
        "circle to mark it as the privileged \"end leaf\" of the construction."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append("| # | Group | Channel | Digits to π | Depth | Size | Source | Expression |")
    lines.append("|---|-------|---------|-------------|-------|------|--------|------------|")
    for k, d in enumerate(found, 1):
        lines.append(
            f"| {k} | {d.hit.group} | {d.hit.channel} | {d.hit.digits} | "
            f"{d.hit.depth} | {d.hit.size} | {d.source} | `{d.hit.expr}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    by_group = group_results(found)
    counter = 0
    for group in GROUP_ORDER:
        bucket = by_group.get(group, [])
        lines.append(f"## {GROUP_TITLE[group]}")
        lines.append("")
        lines.append(GROUP_DESCRIPTION[group])
        lines.append("")
        if not bucket:
            lines.append(
                "_**No trees in this group.**_  "
                "This is consistent with the structural argument in "
                "`validate_eml_general.py`: the EML operator never multiplies, "
                "so an `i·π` term produced by `ln(−1)` can never be flattened "
                "back onto the real line. Without the `C_pi` leaf the search "
                "space cannot synthesize π in this channel; the gallery below "
                "would only contain hand-built constructions that *use* `C_pi`, "
                "which we exclude as the trivial cheat."
            )
            lines.append("")
            continue
        lines.append(f"_{len(bucket)} unique tree(s) in this group._")
        lines.append("")
        for d in bucket:
            counter += 1
            hp_digits = evaluate_high_precision_digits(d.tree, d.hit.channel, dps=hp_dps)
            lines.append(f"### Tree #{counter} — {d.hit.digits} digits to π via `{d.hit.channel}`")
            lines.append("")
            lines.append(f"- **Group**: {d.hit.group}")
            lines.append(f"- **Source**: {d.source}")
            lines.append(f"- **Depth / Size**: {d.hit.depth} / {d.hit.size}")
            lines.append(f"- **Value**: `{d.hit.value_str}`")
            lines.append(
                f"- **Validation**: leading-digit match in `{d.hit.channel}` channel = "
                f"**{d.hit.digits}** at 80 dps; high-precision recheck at {hp_dps} dps "
                f"= **{hp_digits}** digits."
            )
            lines.append(f"- **Code form**: `{d.hit.expr}`")
            lines.append(f"- **EML logic form**: `{render_expression(d.tree)}`")
            lines.append("")
            lines.append("```mermaid")
            lines.append(render_mermaid(d.tree, title=d.hit.expr))
            lines.append("```")
            lines.append("")
    out_path.write_text("\n".join(lines))


def _h(s: str) -> str:
    """HTML-escape a piece of inline text."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_html(found: list[Discovered], html_path: Path, hp_dps: int) -> None:
    """Write a single-file HTML viewer with native HTML structure (no
    in-browser markdown parser).  Mermaid 10 is loaded from CDN and runs
    over `<div class="mermaid">` blocks injected directly below.

    This is intentionally not a markdown roundtrip: marked's renderer API
    has changed across major versions (v5/v8/v10/v15) and silently drops
    fenced-code blocks under some signatures.  Generating HTML server-side
    sidesteps that entirely.
    """
    by_group = group_results(found)

    parts: list[str] = []
    parts.append('<!doctype html>')
    parts.append('<html lang="en">')
    parts.append('<head>')
    parts.append('<meta charset="utf-8">')
    parts.append('<title>Validated π Trees — LSTM-EML Gallery</title>')
    parts.append('<style>')
    parts.append("""
  body { font-family: -apple-system, system-ui, sans-serif;
         max-width: 1100px; margin: 2em auto; padding: 0 1.2em;
         line-height: 1.55; color: #222; }
  h1 { color: #2a2a2a; }
  h2 { color: #2a2a2a; border-bottom: 2px solid #d0d0d0; padding-bottom: .25em;
       margin-top: 2.4em; }
  h3 { color: #2a2a2a; background: #f5f5f8; padding: .35em .6em;
       border-left: 4px solid #b07000; border-radius: 3px; }
  table { border-collapse: collapse; width: 100%; font-size: 0.92em;
          margin: 1em 0; }
  th, td { border: 1px solid #ccc; padding: 5px 8px; text-align: left; }
  th { background: #f0f0f4; }
  code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px;
         font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.9em; }
  ul { margin-top: .3em; }
  .mermaid { background: #fafafa; padding: 1em; border: 1px solid #ddd;
             border-radius: 4px; margin: 1em 0; text-align: center; }
  .empty { background: #fff7e0; border-left: 4px solid #b07000;
           padding: .8em 1em; margin: 1em 0; border-radius: 3px; }
  .meta { font-size: .85em; color: #555; margin-top: 0; }
""")
    parts.append('</style>')
    parts.append('</head><body>')

    parts.append('<h1>Validated π Trees — LSTM-EML Search Gallery</h1>')
    parts.append(
        '<p>Every tree below is a discovery in the EML-only operator family '
        '<code>EML(x, y) = exp(x) − ln(y)</code>. Each one was sampled (or '
        f'hand-derived as a positive-control seed) and validated by re-evaluating '
        f'the tree in <code>mpmath</code> at {hp_dps} decimal digits. The reported '
        'digit count is the leading-digit agreement of the named channel with π.</p>'
    )
    parts.append(
        '<p>Visualization convention (per the project spec): the '
        '<strong>left/exp child</strong> of every <code>EML</code> node is drawn '
        '<em>upward</em> (the exponential grows like a tree trunk), and the '
        '<strong>right/ln child</strong> is drawn <em>to the side</em> (the '
        'logarithm branches out). Constant leaves are rendered as labelled '
        'blocks, and the leaf <code>1</code> is drawn as a green circle to mark '
        'it as the privileged "end leaf" of the construction.</p>'
    )

    # Summary table -------------------------------------------------------- #
    parts.append('<h2>Summary table</h2>')
    parts.append('<table>')
    parts.append(
        '<tr><th>#</th><th>Group</th><th>Channel</th><th>Digits to π</th>'
        '<th>Depth</th><th>Size</th><th>Source</th><th>Expression</th></tr>'
    )
    for k, d in enumerate(found, 1):
        parts.append(
            f'<tr><td>{k}</td><td>{_h(d.hit.group)}</td>'
            f'<td>{_h(d.hit.channel)}</td><td>{d.hit.digits}</td>'
            f'<td>{d.hit.depth}</td><td>{d.hit.size}</td>'
            f'<td>{_h(d.source)}</td>'
            f'<td><code>{_h(d.hit.expr)}</code></td></tr>'
        )
    parts.append('</table>')

    counter = 0
    for group in GROUP_ORDER:
        bucket = by_group.get(group, [])
        # Strip the markdown bold markers when reusing GROUP_TITLE for HTML.
        title = GROUP_TITLE[group].replace("**", "")
        parts.append(f'<h2>{_h(title)}</h2>')
        parts.append(f'<p>{GROUP_DESCRIPTION[group]}</p>')

        if not bucket:
            parts.append(
                '<div class="empty"><strong>No trees in this group.</strong> '
                'This is consistent with the structural argument in '
                '<code>validate_eml_general.py</code>: the EML operator never '
                'multiplies, so an <code>i·π</code> term produced by '
                '<code>ln(−1)</code> can never be flattened back onto the real '
                'line. Without the <code>C_pi</code> leaf the search space '
                'cannot synthesize π in this channel; the gallery below would '
                'only contain hand-built constructions that <em>use</em> '
                '<code>C_pi</code>, which we exclude as the trivial cheat.'
                '</div>'
            )
            continue

        parts.append(f'<p><em>{len(bucket)} unique tree(s) in this group.</em></p>')
        for d in bucket:
            counter += 1
            hp_digits = evaluate_high_precision_digits(d.tree, d.hit.channel, dps=hp_dps)
            parts.append(
                f'<h3>Tree #{counter} — {d.hit.digits} digits to π via '
                f'<code>{_h(d.hit.channel)}</code></h3>'
            )
            parts.append('<ul>')
            parts.append(f'<li><strong>Group</strong>: {_h(d.hit.group)}</li>')
            parts.append(f'<li><strong>Source</strong>: {_h(d.source)}</li>')
            parts.append(
                f'<li><strong>Depth / Size</strong>: {d.hit.depth} / {d.hit.size}</li>'
            )
            parts.append(
                f'<li><strong>Value</strong>: <code>{_h(d.hit.value_str)}</code></li>'
            )
            parts.append(
                f'<li><strong>Validation</strong>: leading-digit match in '
                f'<code>{_h(d.hit.channel)}</code> channel = '
                f'<strong>{d.hit.digits}</strong> at 80 dps; high-precision '
                f'recheck at {hp_dps} dps = <strong>{hp_digits}</strong> '
                f'digits.</li>'
            )
            parts.append(
                f'<li><strong>Code form</strong>: <code>{_h(d.hit.expr)}</code></li>'
            )
            parts.append(
                f'<li><strong>EML logic form</strong>: '
                f'<code>{_h(render_expression(d.tree))}</code></li>'
            )
            parts.append('</ul>')

            mermaid_src = render_mermaid(d.tree, title=d.hit.expr)
            parts.append(f'<div class="mermaid">{_h(mermaid_src)}</div>')

    # Mermaid bootstrap ---------------------------------------------------- #
    parts.append("""
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
  mermaid.initialize({ startOnLoad: false, theme: "default", securityLevel: "loose" });
  await mermaid.run({ querySelector: ".mermaid" });
</script>
""")
    parts.append('</body></html>')
    html_path.write_text("\n".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20,
                    help="target number of unique trees to collect")
    ap.add_argument("--train-steps", type=int, default=800)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--samples", type=int, default=1024)
    ap.add_argument("--min-digits", type=int, default=6)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--forbid-e", action="store_true")
    ap.add_argument("--hp-dps", type=int, default=200,
                    help="high-precision dps for the validation recheck")
    ap.add_argument("--out-md",   default="output/validated_trees.md")
    ap.add_argument("--out-html", default="output/validated_trees.html")
    args = ap.parse_args()

    found = discover(
        n_target=args.n,
        train_steps=args.train_steps,
        samples_per_round=args.samples,
        n_rounds=args.rounds,
        temperatures=(1.0, 1.2, 1.5, 1.8, 2.2, 2.6),
        min_digits=args.min_digits,
        device_req=args.device,
        seed=args.seed,
        forbid_e_leaf=args.forbid_e,
    )
    if not found:
        print("[build_report] no trees found — aborting")
        sys.exit(1)

    by_group = group_results(found)
    print("\n[build_report] distribution by group:")
    for g in GROUP_ORDER:
        print(f"  {g:>10s}: {len(by_group.get(g, []))}")

    md_path = ROOT / args.out_md
    html_path = ROOT / args.out_html
    md_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(found, md_path, args.hp_dps)
    write_html(found, html_path, args.hp_dps)
    print(f"\n[build_report] wrote {md_path}")
    print(f"[build_report] wrote {html_path}")


if __name__ == "__main__":
    main()
