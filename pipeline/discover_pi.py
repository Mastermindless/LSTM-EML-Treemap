"""Iterative LSTM-EML driver that mines unique pi-discovering trees.

Strategy
--------
1. Train the LSTM-EML generator briefly on target=`pi` (configurable steps,
   defaults to a short run that exposes π via the `ln(-1) = i·π` family).
2. Run repeated sampling rounds with rising temperature/decoder noise to
   diversify rollouts.
3. Parse each rollout, evaluate with mpmath, classify the best channel match
   to π (Re / Im / |·| / |Im|), keep only those that match ≥ MIN_DIGITS.
4. De-duplicate by canonical `repr(tree)` so we collect *structurally
   distinct* derivations.

The function returns a list of `PiHit`-augmented records:
    {tree, hit, source}
where `source` is "trained-sample" or "seed-construction" (the optional
hand-built positive controls that the user explicitly requested as part of
the gallery — see `SEED_CONSTRUCTIONS`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src_tree_search"))

from config import CONFIG  # noqa: E402
from eml_tree import EML, Constant, EMLNode  # noqa: E402
from loss import evaluate_rollout, reinforce_loss  # noqa: E402
from lstm_generator import LSTM_EML_Generator  # noqa: E402
from targets import list_targets  # noqa: E402
from tokenizer import (  # noqa: E402
    NAME_TO_ID, disabled_leaves_for_target, parse_prefix,
)

from pipeline.tree_validation import PiHit, evaluate_pi_hit


@dataclass
class Discovered:
    tree: EMLNode
    hit: PiHit
    source: str


def _pick_device(req: str) -> torch.device:
    if req == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if req == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _train_briefly(
    target_name: str,
    steps: int,
    batch: int,
    device: torch.device,
    extra_disabled: set[int] | None = None,
) -> LSTM_EML_Generator:
    targets = list_targets()
    target_id = targets.index(target_name)

    model = LSTM_EML_Generator(
        n_targets=len(targets),
        embed_dim=CONFIG.embed_dim,
        hidden=CONFIG.hidden,
        num_layers=CONFIG.num_layers,
    ).to(device)

    optim = torch.optim.Adam(model.parameters(), lr=CONFIG.lr)
    disabled = disabled_leaves_for_target(target_name) | (extra_disabled or set())

    digits_n = CONFIG.target_digits
    for step in range(steps):
        target_ids = torch.full((batch,), target_id, dtype=torch.long)
        rollout = model.sample(
            target_ids, max_tokens=CONFIG.max_tokens,
            disabled_leaves=disabled,
        )
        rewards = evaluate_rollout(
            rollout.tokens, rollout.lengths,
            target_name=target_name,
            target_digits_n=digits_n,
            mp_dps=CONFIG.mp_dps,
            invalid_reward=CONFIG.invalid_reward,
        )
        loss, stats = reinforce_loss(
            rollout.log_probs, rewards, rollout.entropies,
            CONFIG.entropy_beta,
        )
        optim.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), CONFIG.grad_clip)
        optim.step()

        if step % 50 == 0 or step == steps - 1:
            print(
                f"  [train] step={step:4d}  r_mean={stats['reward_mean']:.3f}  "
                f"r_max={stats['reward_max']:.3f}  H={stats['entropy']:.2f}"
            )
    return model


def _sample_pool(
    model: LSTM_EML_Generator,
    target_name: str,
    n_samples: int,
    temperature: float,
    device: torch.device,
    extra_disabled: set[int] | None = None,
) -> list[EMLNode]:
    targets = list_targets()
    target_id = targets.index(target_name)
    target_ids = torch.full((n_samples,), target_id, dtype=torch.long)
    disabled = disabled_leaves_for_target(target_name) | (extra_disabled or set())
    with torch.no_grad():
        rollout = model.sample(
            target_ids,
            max_tokens=CONFIG.max_tokens,
            disabled_leaves=disabled,
            temperature=temperature,
        )
    trees: list[EMLNode] = []
    tokens = rollout.tokens.cpu().tolist()
    lengths = rollout.lengths.cpu().tolist()
    for seq, L in zip(tokens, lengths):
        tree = parse_prefix(seq[:L])
        if tree is not None:
            trees.append(tree)
    return trees


# --------------------------------------------------------------------------- #
# Hand-derived positive constructions — the canonical pi-from-EML identities
# the user asked us to keep visible alongside model finds.  Each of these is
# *provably* π in some channel and gives the gallery a controlled baseline.
# --------------------------------------------------------------------------- #
def _C(label: str, value):
    return Constant(value, label=label)


def _zero():    return _C("0", 0)
def _one():     return _C("1", 1)
def _neg_one(): return _C("-1", -1)
def _two():     return _C("2", 2)
def _e():
    import mpmath
    return _C("e", mpmath.e)
def _i():       return _C("i", complex(0, 1))
def _neg_i():   return _C("-i", complex(0, -1))


def _seed_constructions() -> list[EMLNode]:
    """Hand-built π identities, all using only the EML operator + base leaves.

    Every construction here lands π in either the imaginary part (via
    ln(-1) = i·π), the |Im| channel, or the magnitude (Pythagoras) channel.
    """
    out: list[EMLNode] = []

    # 1) EML(0, -1) = exp(0) - ln(-1) = 1 - i*pi    → Im channel = -pi, |Im| = pi
    out.append(EML(_zero(), _neg_one()))

    # 2) EML(1, -1) = e - i*pi        → Re=e, Im=-pi
    out.append(EML(_one(), _neg_one()))

    # 3) EML(EML(0, 1), -1) = 1 - i*pi  (same Im, different left subtree)
    out.append(EML(EML(_zero(), _one()), _neg_one()))

    # 4) EML(EML(1, 1), -1) = e - i*pi  (e expressed as EML(1,1))
    out.append(EML(EML(_one(), _one()), _neg_one()))

    # 5) EML(EML(0, e), -1) = 0 - i*pi  → pure i*pi
    out.append(EML(EML(_zero(), _e()), _neg_one()))

    # 6) EML(EML(2, 1), -1) = exp(2) - i*pi
    out.append(EML(EML(_two(), _one()), _neg_one()))

    # 7) EML(EML(EML(0, e), 1), -1) = exp(0) - i*pi = 1 - i*pi
    out.append(EML(EML(EML(_zero(), _e()), _one()), _neg_one()))

    # 8) EML(-1, -1) = exp(-1) - i*pi
    out.append(EML(_neg_one(), _neg_one()))

    # 9) EML(EML(-1, -1), -1) = exp(exp(-1) - i*pi) - i*pi  → still pi in |Im|
    out.append(EML(EML(_neg_one(), _neg_one()), _neg_one()))

    # 10) EML(0, EML(EML(0, EML(pi, 1)), 1))  — uses C_pi (control)
    #     Skipped here because C_pi is the trivial cheat the user excluded.

    # 11) EML(i, -1) = exp(i) - i*pi  → Im = sin(1) - pi, not a clean hit
    #     Skipped.

    # 12) EML(EML(i, i), -1) = (exp(i) - ln(i)) result then minus i*pi.
    #     This was an LSTM find — keep as model-only.

    return out


# --------------------------------------------------------------------------- #
# Main discovery driver
# --------------------------------------------------------------------------- #
def discover(
    n_target: int = 20,
    train_steps: int = 800,
    samples_per_round: int = 1024,
    n_rounds: int = 4,
    temperatures: tuple[float, ...] = (1.0, 1.2, 1.5, 1.8),
    min_digits: int = 6,
    device_req: str = "mps",
    seed: int = 0,
    forbid_e_leaf: bool = False,
) -> list[Discovered]:
    """Run the full discovery loop.

    n_target          stop early once this many unique trees have been found
    train_steps       LSTM-EML training steps (REINFORCE on target=pi)
    samples_per_round number of rollouts per sampling round
    n_rounds          how many rounds (each round can use a different temp)
    temperatures      one temperature per round (cycled if shorter)
    min_digits        minimum matching digits in any channel to count as "hits π"
    forbid_e_leaf     also disable C_e during search (forces purer "EML+1"-style trees)
    """
    torch.manual_seed(seed)
    device = _pick_device(device_req)
    print(f"[discover] device={device} train_steps={train_steps} n_target={n_target}")

    extra_disabled: set[int] = set()
    if forbid_e_leaf:
        extra_disabled.add(NAME_TO_ID["C_e"])

    print(f"[discover] training LSTM briefly...")
    model = _train_briefly("pi", train_steps, CONFIG.batch_size, device, extra_disabled)
    model.eval()

    seen: dict[str, Discovered] = {}

    # Seeds first — these guarantee we have at least the canonical
    # constructions in the gallery before any LSTM noise.
    for tree in _seed_constructions():
        hit = evaluate_pi_hit(tree, min_digits=min_digits)
        if hit is None:
            continue
        key = repr(tree)
        if key not in seen:
            seen[key] = Discovered(tree=tree, hit=hit, source="seed-construction")

    print(f"[discover] {len(seen)} hits after seeds")

    for r in range(n_rounds):
        if len(seen) >= n_target:
            break
        temp = temperatures[r % len(temperatures)]
        print(f"[discover] round {r+1}/{n_rounds}  temp={temp}  pool={samples_per_round}")
        trees = _sample_pool(model, "pi", samples_per_round, temp, device, extra_disabled)
        new_hits = 0
        for tree in trees:
            hit = evaluate_pi_hit(tree, min_digits=min_digits)
            if hit is None:
                continue
            key = repr(tree)
            if key in seen:
                continue
            seen[key] = Discovered(tree=tree, hit=hit, source="trained-sample")
            new_hits += 1
        print(f"[discover]   added {new_hits} new unique trees (total={len(seen)})")

    discovered = sorted(
        seen.values(),
        key=lambda d: (-d.hit.digits, d.hit.size, d.hit.depth),
    )[:n_target]
    print(f"[discover] returning {len(discovered)} trees")
    return discovered


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--train-steps", type=int, default=800)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--samples", type=int, default=1024)
    ap.add_argument("--min-digits", type=int, default=6)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--forbid-e", action="store_true",
                    help="also disable C_e leaf — force purer EML+1 trees")
    args = ap.parse_args()

    out = discover(
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
    for d in out:
        print(f"  {d.hit.digits:>2d} digits  {d.hit.channel:>6s}  ({d.source}) {d.hit.expr}")
