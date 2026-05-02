"""Render an EMLNode tree as a Mermaid flowchart.

Visual logic (per the task spec):
    EML(x, y) := exp(x) - ln(y)

    exp(x)  = "branch up"
    ln(y)   = "branch sideways / right"

Mermaid does not natively support per-edge direction control inside one
flowchart, but `subgraph` blocks each carry an independent `direction`.
We exploit that: every EML node becomes a subgraph with `direction LR`
that holds the EML node, the right-child (-ln) subgraph to the right, and
nests the left-child (exp) subgraph in a `direction TB` outer scope so it
appears above.

Concretely, for each EML node we emit:

    subgraph emlN [" "]
      direction TB
      subgraph emlN_top [" "]
        direction LR
        ...rendered LEFT subtree...
      end
      subgraph emlN_bot [" "]
        direction LR
        emlN_node((EML))
        ...rendered RIGHT subtree...
      end
    end

This makes the **left/exp** child stack visually upward and the
**right/ln** child stretch to the right of the EML node — matching the
"exp grows up, ln grows right" convention.

Leaves render as small labelled boxes; the constant `1` is given a
distinct shape (rounded leaf) per the user's spec ("number 1 will be
encoded also in the plot as some sort end leaf").
"""
from __future__ import annotations

import sys
from itertools import count
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src_tree_search"))

from eml_tree import EML, Constant, EMLNode  # noqa: E402


_LEAF_SHAPES = {
    "1":   ('(("', '"))'),     # circle  — special "end leaf" for 1
    "0":   ('["', '"]'),
    "-1":  ('[/"', '"/]'),
    "2":   ('[/"', '"/]'),
    "i":   ('{{"', '"}}'),
    "-i":  ('{{"', '"}}'),
    "e":   ('[("', '")]'),
    "pi":  ('(("', '"))'),
}
_DEFAULT_SHAPE = ('["', '"]')


def _leaf_shape(label: str) -> tuple[str, str]:
    return _LEAF_SHAPES.get(label, _DEFAULT_SHAPE)


def _node_label(c: Constant) -> str:
    label = getattr(c, "_label", None)
    if label is None:
        label = str(c.value)
    # Mermaid-friendly cosmetics
    return {
        "-1": "−1",
        "-i": "−i",
        "pi": "π",
    }.get(label, label)


def render_mermaid(tree: EMLNode, *, title: str | None = None) -> str:
    """Return a Mermaid flowchart string for `tree`.

    Layout: outer flowchart is `TB` (top-to-bottom layout), with each EML
    node wrapping its left subtree in a TB sub-stack (so exp grows up
    when read root-first) and its right subtree in an LR row (so ln
    grows sideways).
    """
    ids = count(1)
    edges: list[str] = []
    blocks: list[str] = []

    def fresh(prefix: str) -> str:
        return f"{prefix}{next(ids)}"

    def render(node: EMLNode, parent_class: str) -> str:
        """Render a node, return its mermaid id."""
        if isinstance(node, Constant):
            nid = fresh("L")
            label = _node_label(node)
            l_open, l_close = _leaf_shape(label)
            cls = "leafone" if label == "1" else "leaf"
            blocks.append(f'    {nid}{l_open}{label}{l_close}:::{cls}')
            return nid

        # EML node: render left (exp) subtree, then right (ln) subtree.
        eml_id = fresh("E")
        left_id = render(node.left, "exp")
        right_id = render(node.right, "ln")

        blocks.append(f'    {eml_id}(("EML")):::eml')
        # Edge from left subtree → EML (drawn going *up* visually thanks to BT).
        edges.append(f'    {left_id} -->|"exp"| {eml_id}')
        # Edge from EML → right subtree (sideways, "−ln" branch).
        edges.append(f'    {eml_id} -->|"−ln"| {right_id}')
        return eml_id

    root_id = render(tree, "root")

    header = []
    if title:
        header.append(f"%% {title}")
    header.append("flowchart BT")
    body = (
        header
        + blocks
        + edges
        + [
            "",
            "    classDef eml fill:#ffe8b3,stroke:#b07000,stroke-width:1.5px,color:#222;",
            "    classDef leaf fill:#e8f0ff,stroke:#3060a0,color:#222;",
            "    classDef leafone fill:#cdeccd,stroke:#2f7a2f,stroke-width:2px,color:#0d2;",
            f"    style {root_id} stroke-width:3px;",
        ]
    )
    return "\n".join(body)


def render_expression(tree: EMLNode) -> str:
    """Pretty `exp(...) - ln(...)` form.  Recurses through nested EMLs."""
    if isinstance(tree, Constant):
        return _node_label(tree)
    return f"(exp({render_expression(tree.left)}) − ln({render_expression(tree.right)}))"


if __name__ == "__main__":
    import mpmath
    # Demo: EML(0, -1)  = 1 − iπ
    t = EML(Constant(0, label="0"), Constant(-1, label="-1"))
    print(render_mermaid(t, title="EML(0,-1)  = 1 − iπ"))
    print()
    print(render_expression(t))
