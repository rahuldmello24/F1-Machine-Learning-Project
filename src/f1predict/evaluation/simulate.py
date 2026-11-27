"""Turn per-driver (strength, retirement probability) into finishing-position
probabilities by simulating the race many times.

The race model (a "hurdle" Plackett-Luce model)
-----------------------------------------------
1. Each car independently retires with probability ``p_dnf``.
2. The cars that finish are ordered by a Plackett-Luce model: the
   winner is drawn with probability proportional to ``exp(strength)``,
   then second place from the remaining cars, and so on.
3. Retired cars are placed behind every finisher, in random order.

Step 2 is simulated with the *Gumbel-max trick*: adding independent
Gumbel noise to each strength and sorting gives exactly a Plackett-Luce
sample, so thousands of races take milliseconds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_positions(strength: np.ndarray, p_dnf: np.ndarray, n_sims: int = 20_000,
                       rng: np.random.Generator | None = None) -> np.ndarray:
    """Return an (n_drivers, n_drivers) matrix P where P[i, k] is the
    probability that driver i finishes in position k+1."""
    rng = rng or np.random.default_rng(0)
    n = len(strength)
    gumbel = rng.gumbel(size=(n_sims, n))
    score = strength[None, :] + gumbel
    dnf = rng.random((n_sims, n)) < p_dnf[None, :]
    # retired cars sort behind all finishers (still randomly among themselves)
    score = np.where(dnf, score - 1e6, score)
    order = np.argsort(-score, axis=1)  # order[s, k] = driver in position k+1
    probs = np.zeros((n, n))
    for k in range(n):
        probs[:, k] = np.bincount(order[:, k], minlength=n)
    return probs / n_sims


def position_table(pred: pd.DataFrame, n_sims: int = 20_000, seed: int = 0) -> pd.DataFrame:
    """Add win/podium/points/expected-position columns to a prediction frame
    with ``strength`` and ``p_dnf`` for the drivers of a single race."""
    P = simulate_positions(pred["strength"].to_numpy(float), pred["p_dnf"].to_numpy(float),
                           n_sims, np.random.default_rng(seed))
    out = pred.copy()
    out["p_win"] = P[:, 0]
    out["p_podium"] = P[:, :3].sum(axis=1)
    out["p_points"] = P[:, :10].sum(axis=1)
    out["exp_position"] = P @ np.arange(1, P.shape[1] + 1)
    out.attrs["position_probs"] = P
    return out
