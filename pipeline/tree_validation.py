"""Validate an EML tree as a candidate for pi.

A "pi hit" is decided per-channel of the (possibly complex) value:

    Re(v)        — real part
    Im(v)        — imaginary part
    abs_im(v)    — |Im(v)|, useful when ln(-1) gives -i*pi
    abs(v)       — sqrt(Re^2 + Im^2)  ("Pythagoras")

The same metric is used by `validate_eml_general.py`; we reuse its style but
keep this module import-safe (no embedded MODEL_OUTPUT, no argparse side
effects) so the rest of the pipeline can call it.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import mpmath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src_tree_search"))

from eml_tree import EML, Constant, EMLNode, evaluate_tree, tree_depth, tree_size  # noqa: E402

mpmath.mp.dps = 80

PI = mpmath.pi


@dataclass
class PiHit:
    expr: str                # human-readable EML(...) form
    channel: str             # "Re" | "Im" | "abs" | "abs_im"
    group: str               # "real" | "imaginary" | "pythagoras"
    digits: int              # leading matching digits to pi
    abs_err: float           # absolute error vs pi in that channel
    value_str: str           # short-form numeric value (for the report)
    depth: int
    size: int


# Map channel → display group requested by the user spec
_CHANNEL_GROUP = {
    "Re": "real",
    "Im": "imaginary",
    "abs_im": "imaginary",
    "abs": "pythagoras",
}


def _components(val) -> dict[str, "mpmath.mpf"]:
    if isinstance(val, mpmath.mpc):
        re_, im_ = mpmath.re(val), mpmath.im(val)
    else:
        re_, im_ = mpmath.mpf(val), mpmath.mpf(0)
    return {
        "Re":     re_,
        "Im":     im_,
        "abs":    mpmath.sqrt(re_ * re_ + im_ * im_),
        "abs_im": abs(im_),
    }


def _matching_digits(a, b, max_digits: int = 50) -> int:
    if a == 0 and b == 0:
        return max_digits
    if a == 0 or b == 0:
        return 0
    rel = abs(mpmath.mpf(a) - mpmath.mpf(b)) / max(abs(mpmath.mpf(a)), abs(mpmath.mpf(b)))
    if rel == 0:
        return max_digits
    return max(0, int(-mpmath.log10(rel)))


def _format_value(v) -> str:
    if isinstance(v, mpmath.mpc):
        return f"({mpmath.nstr(mpmath.re(v), 12)} + {mpmath.nstr(mpmath.im(v), 12)}j)"
    return mpmath.nstr(v, 12)


def evaluate_pi_hit(tree: EMLNode, min_digits: int = 6, dps: int = 80) -> PiHit | None:
    """Return a PiHit describing the strongest channel match, or None."""
    val = evaluate_tree(tree, dps)
    if val is None or (isinstance(val, mpmath.mpc) and (mpmath.isnan(mpmath.re(val)) or mpmath.isinf(mpmath.re(val)))):
        return None
    if not isinstance(val, mpmath.mpc) and (mpmath.isnan(val) or mpmath.isinf(val)):
        return None

    comps = _components(val)
    best: PiHit | None = None
    for ch, cval in comps.items():
        try:
            err = float(abs(cval - PI))
        except (ValueError, OverflowError):
            continue
        digits = _matching_digits(cval, PI)
        if digits < min_digits:
            continue
        if best is None or digits > best.digits or (digits == best.digits and err < best.abs_err):
            best = PiHit(
                expr=repr(tree),
                channel=ch,
                group=_CHANNEL_GROUP[ch],
                digits=digits,
                abs_err=err,
                value_str=_format_value(val),
                depth=tree_depth(tree),
                size=tree_size(tree),
            )
    return best


def evaluate_high_precision_digits(tree: EMLNode, channel: str, dps: int = 200) -> int:
    """Re-evaluate at very high precision; return digits-of-π in the chosen channel."""
    val = evaluate_tree(tree, dps)
    if val is None:
        return 0
    prev = mpmath.mp.dps
    mpmath.mp.dps = dps
    try:
        comps = _components(val)
        cval = comps[channel]
        return _matching_digits(cval, mpmath.pi, max_digits=dps - 5)
    finally:
        mpmath.mp.dps = prev
