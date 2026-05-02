# LSTM-EML Tree Visualization Pipeline

A reproducible pipeline that **mines, validates, groups, and visualises**
unique nested expressions in the **EML operator family**

```
EML(x, y) := exp(x) − ln(y)
```

that numerically reproduce **π** to many leading digits. The original LSTM-EML
search code lives in [`src_tree_search/`](src_tree_search/) and is taken from
[Mastermindless/LSTM-EML-search-tree](https://github.com/Mastermindless/LSTM-EML-search-tree).
This repo wraps that search with a **discovery → validation → grouping →
visualisation** pipeline that emits a publication-style gallery of ≥ 20
distinct π-trees.

---

## What you get

Running the pipeline produces:

| File | Purpose |
|---|---|
| [`output/validated_trees.md`](output/validated_trees.md) | The full gallery — Markdown with embedded Mermaid plots, one section per tree, grouped by which complex-number channel carries π. |
| [`output/validated_trees.html`](output/validated_trees.html) | Self-contained browser viewer — opens directly, renders Mermaid via CDN. |
| `checkpoints/lstm_eml_pi.pt` *(if you run `train.py` directly)* | Saved LSTM weights from the underlying search. |

The gallery contains, for **every tree**:
- the **code form** (`EML(...)`, drop-in to `validate_eml_general.py`),
- the **EML-logic form** (`(exp(...) − ln(...))`),
- the **mpmath validation**: leading-digit match at 80 dps and a re-evaluation at 200 dps,
- the **closest-channel match** (Re / Im / |Im| / |·|),
- a **Mermaid plot** with the visualisation convention requested in the spec
  (exp child grows up, ln child grows sideways, leaf `1` highlighted).

---

## How to run

```bash
# default: 24 trees, 400 training steps, GPU/MPS, ~3 minutes total on Apple Silicon
python3 -m pipeline.build_report --n 24 --train-steps 400 --device mps --seed 7

# quick smoke run, CPU-only
python3 -m pipeline.build_report --n 20 --train-steps 60 --rounds 2 --samples 256 --device cpu

# example run on MPS
python3 -m pipeline.build_report --n 200 --train-steps 500 --rounds 8096 --device mps --seed 1984


# a more aggressive search:
python -m pipeline.build_report \
    --n 30 --train-steps 1500 --rounds 8 --samples 2048 \
    --min-digits 4 --hp-dps 400 --seed 0
```

Useful flags:

| Flag | What it does |
|---|---|
| `--n` | target number of unique trees (the gallery stops growing once reached) |
| `--train-steps` | REINFORCE steps for the LSTM-EML controller |
| `--rounds` / `--samples` | post-training sampling rounds and pool size per round |
| `--min-digits` | minimum digit-match in any channel to count as a "π hit" |
| `--forbid-e` | also disable the `C_e` constant leaf (forces purer "EML + 1" trees) |
| `--hp-dps` | high-precision dps for the validation re-check |
| `--seed` | torch seed (changing this is the cheapest way to broaden the gallery) |

---

## Pipeline architecture

```
                    ┌──────────────────────────┐
                    │  src_tree_search/        │   ← upstream LSTM-EML
                    │   tokenizer / lstm_gen / │
                    │   loss / targets / train │
                    └─────────────┬────────────┘
                                  │
   ┌──────────────────────────────┼──────────────────────────────┐
   │                              ▼                              │
   │   pipeline/discover_pi.py                                   │
   │   ─ trains the LSTM briefly on target=π (C_pi disabled)     │
   │   ─ runs N sampling rounds at rising temperature            │
   │   ─ parses every rollout, dedupes by canonical repr         │
   │   ─ seeds with hand-built positive-control identities        │
   │                              │                              │
   │                              ▼                              │
   │   pipeline/tree_validation.py                                │
   │   ─ evaluates each tree at 80 dps via mpmath                │
   │   ─ projects onto (Re, Im, |Im|, |·|) channels              │
   │   ─ keeps trees that match π in any channel ≥ min-digits    │
   │                              │                              │
   │                              ▼                              │
   │   pipeline/mermaid_render.py                                 │
   │   ─ tree → Mermaid `flowchart BT` with                      │
   │       exp-child edge labelled "exp"  (drawn upward)         │
   │       ln-child edge labelled "−ln"  (drawn sideways)        │
   │       leaf `1` shown as a green circle (privileged leaf)    │
   │                              │                              │
   │                              ▼                              │
   │   pipeline/build_report.py                                   │
   │   ─ groups by channel-meaning:                              │
   │       I.  real      (Re part = π)                            │
   │       II. imaginary (Im or |Im| = π)                         │
   │       III.pythagoras (|v| = π)                               │
   │   ─ emits validated_trees.md   (markdown + mermaid)         │
   │   ─ emits validated_trees.html (single-file viewer)         │
   └──────────────────────────────────────────────────────────────┘
```

---

## Visualisation convention

Every Mermaid plot in the gallery is rendered as a `flowchart BT`
(bottom-to-top). For each `EML` node:

- the **left child** carries the argument of `exp(·)` and is drawn **upward**
  (the exponential branch grows like a trunk);
- the **right child** carries the argument of `−ln(·)` and is drawn
  **sideways** (the logarithmic branch spreads out);
- the leaf **`1`** is rendered as a **green circle** to mark it as the
  privileged "end leaf" of the construction (per the project spec, *"the
  EML operator and number 1 will be elements to draw the tree"*).

Mermaid does not natively support per-edge layout direction, so we lean on
its automatic graph layout under `BT` and rely on the edge labels (`exp`
vs `−ln`) plus consistent node shapes/colors to make the convention
visually unambiguous.

---

## Why three groups?

The reward function in [`src_tree_search/loss.py`](src_tree_search/loss.py)
is **channel-agnostic**: it returns the **best** prefix-digit match across
the three projections `{Re(v), Im(v), |v|}` for each candidate value `v`.
This is exactly the logic the user asked us to surface in the gallery — so
we group every discovery by which channel carries π:

| Group | Channel(s) | Mathematical interpretation |
|---|---|---|
| **I. real** | `Re` | `Re(v) ≈ π` — π lives on the real axis |
| **II. imaginary** | `Im`, `abs_im` | `Im(v) ≈ π` or `|Im(v)| ≈ π` — the bread-and-butter `ln(−1) = i·π` family |
| **III. pythagoras** | `abs` | `|v| = √(Re² + Im²) ≈ π` — the deepest finds; both real and imaginary parts have been shaped to land their RSS on π |

A note on group I: with the `C_pi` leaf removed (the trivial cheat), a
purely-real π is **structurally unreachable** in the EML-only operator
family — `EML` never multiplies, so an `i·π` produced by `ln(−1)` cannot
be flattened back onto the real line. The pipeline reports this
explicitly when group I is empty, rather than silently dropping the section.

---

## Validation methodology

The validation re-uses the per-component matching approach of
[`validate_eml_general.py`](validate_eml_general.py):

1. **Evaluate** the tree in `mpmath` at 80 working digits.
2. **Project** the (potentially complex) value onto the four channels
   `Re`, `Im`, `|Im|`, `|·|`.
3. **Match** each channel's leading significant digits against `mpmath.pi`.
4. **Pick** the channel with the highest digit-match — that determines
   both the *digits-to-π* score and the *group* the tree lands in.
5. **Re-evaluate** at 200 dps as a sanity check; if the model has truly
   landed an exact identity (e.g. `Im(EML(0, −1)) = −π`), the digit count
   should grow with `dps` rather than saturate.

Each gallery entry shows both numbers (80-dps and 200-dps) so it is easy
to tell true identities from numerical coincidences.

---

## Reproducibility

- All randomness is seeded via `--seed` (`torch.manual_seed`).
- The LSTM-EML search uses the existing hyperparameters from
  [`src_tree_search/config.py`](src_tree_search/config.py); you can override
  `--train-steps`, `--rounds`, and `--samples` from the CLI.
- Hand-built positive-control trees live in
  [`pipeline/discover_pi.py::_seed_constructions`](pipeline/discover_pi.py)
  and seed the gallery deterministically — the LSTM-EML search adds
  diversity on top.

---

## Repository layout

```
LSTM_EML_TREE_VIS/
├── README.md                     ← this file
├── src_tree_search/              ← upstream LSTM-EML search
│   ├── config.py
│   ├── eml_tree.py               ← EML / Constant / EMLNode
│   ├── inference.py
│   ├── lstm_generator.py         ← arity-masked LSTM controller
│   ├── loss.py                   ← channel-agnostic REINFORCE reward
│   ├── targets.py                ← π / e / φ / γ / … target registry
│   ├── tokenizer.py              ← prefix parser, vocabulary
│   └── train.py
├── pipeline/                     ← this project
│   ├── discover_pi.py            ← train + sample + dedupe → π hits
│   ├── tree_validation.py        ← per-channel mpmath matcher
│   ├── mermaid_render.py         ← tree → flowchart BT
│   └── build_report.py           ← orchestrator: → md + html
└── 200_ways_to_Pi/
    ├── validated_trees.md        ← the gallery (markdown)
	├── index.md        		← the gallery (markdown)
    └── validated_trees.html      ← the gallery (single-file viewer)
```

---

## Design decisions worth keeping

- **`C_pi` is the trivial cheat — always disabled.** The whole point of
  the search is to *re-derive* π, not to look it up. The upstream
  `tokenizer.py::disabled_leaves_for_target` already does this; we keep
  it on by default and offer `--forbid-e` for an even purer "EML + 1"
  family.
- **Seed constructions are kept in the gallery.** The user explicitly
  asked for hand-derived π identities to be part of the visualisation;
  these provide a controlled baseline alongside the LSTM finds and are
  tagged `seed-construction` in the summary table.
- **Group I is allowed to be empty.** The structural argument (no
  multiplication ⇒ no flattening of `i·π`) is reported as a
  *finding*, not silently swept under the rug.
- **All four channels (Re / Im / |Im| / |·|) are checked**, but a tree
  is grouped only by its *winning* channel, so the same tree never
  appears in two groups.
- **Tree shape ↔ channel.** The depth/size columns of the summary table
  expose the structural difference the user wants to see: imaginary-channel
  hits are usually shallow (depth ≤ 2, the bare `EML(·, −1)` shape),
  whereas Pythagoras hits are deeper (depth ≥ 3, two nested `−ln(−1)`
  contributions whose RSS happens to land on π).
