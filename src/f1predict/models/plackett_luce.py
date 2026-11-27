"""Fitting a linear Plackett-Luce model.

Each driver's strength is a weighted sum of their features,
``strength = X @ w``. The probability of an observed finishing order
(1st, 2nd, ..., last finisher) is

    P(order) = prod_k  exp(s_k) / sum_{j >= k} exp(s_j)

i.e. the winner is "chosen" from the whole field, second place from the
rest, and so on. We pick ``w`` to maximise the log of this probability
summed over all training races (maximum likelihood), with a small L2
penalty to keep weights sensible. The gradient is exact, so L-BFGS
converges in well under a second for thousands of races.

Only *classified finishers* enter this likelihood: whether a car
finishes at all is modelled separately (p_dnf), which is what makes the
overall model a hurdle model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def _pad(df: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Races -> padded (R, M, F) design tensor ordered by finishing order."""
    df = df.sort_values(["race_id", "finish_order"])
    groups = [g[features].to_numpy(float) for _, g in df.groupby("race_id", sort=False)]
    R, M, F = len(groups), max(len(g) for g in groups), len(features)
    X = np.zeros((R, M, F))
    mask = np.zeros((R, M), dtype=bool)
    for i, g in enumerate(groups):
        X[i, : len(g)] = g
        mask[i, : len(g)] = True
    return X, mask


def _nll_and_grad(w: np.ndarray, X: np.ndarray, mask: np.ndarray, l2: float):
    U = X @ w
    U = np.where(mask, U, -np.inf)
    # log-sum-exp over "everyone not yet placed": reverse cumulative
    cum = np.logaddexp.accumulate(U[:, ::-1], axis=1)[:, ::-1]
    ll_terms = np.where(mask, U - np.where(mask, cum, 0.0), 0.0)
    nll = -ll_terms.sum() + l2 * (w @ w)

    # gradient: x_k - E[x | chosen among j >= k]
    M = X.shape[1]
    upper = np.triu(np.ones((M, M), dtype=bool))  # j >= k
    with np.errstate(invalid="ignore"):
        A = np.exp(U[:, None, :] - cum[:, :, None])  # (R, k, j)
    A = np.where(upper[None] & mask[:, None, :] & mask[:, :, None], A, 0.0)
    E = A @ X  # (R, M, F)
    g = ((X - E) * mask[..., None]).sum(axis=(0, 1))
    return nll, -g + 2 * l2 * w


def fit_pl(df: pd.DataFrame, features: list[str], l2: float = 1e-3) -> np.ndarray:
    fin = df[df["finished"]]
    fin = fin[fin.groupby("race_id")["driver"].transform("size") >= 2]
    X, mask = _pad(fin, features)
    res = minimize(_nll_and_grad, np.zeros(len(features)), args=(X, mask, l2), jac=True, method="L-BFGS-B")
    return res.x


def pl_loglik(df: pd.DataFrame, features: list[str], w: np.ndarray) -> float:
    fin = df[df["finished"]]
    X, mask = _pad(fin, features)
    return -_nll_and_grad(w, X, mask, 0.0)[0]
