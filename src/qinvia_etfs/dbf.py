"""Direction–Breadth Factor (DBF) for positive wealth series.

DBF is computed from periodic log returns.  The signed form combines net
direction with the effective breadth of return magnitudes and is the form used
for ETF-to-SPY comparisons in this project.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def dbf_from_log_returns(log_returns: pd.Series | np.ndarray) -> dict[str, float]:
    """Return direction, breadth, signed DBF and absolute DBF."""

    returns = np.asarray(log_returns, dtype=float)
    if returns.ndim != 1 or returns.size == 0 or not np.isfinite(returns).all():
        raise ValueError("log_returns must be a non-empty one-dimensional finite series")

    l1 = float(np.abs(returns).sum())
    l2 = float(np.square(returns).sum())
    if l2 == 0.0:
        direction = breadth = signed = 0.0
    else:
        direction = float(returns.sum() / l1)
        breadth = float(np.clip(l1**2 / (returns.size * l2), 0.0, 1.0))
        signed = float(np.clip(direction * breadth, -1.0, 1.0))
    return {
        "direction": direction,
        "breadth": breadth,
        "dbf_signed": signed,
        "dbf": abs(signed),
    }


def dbf_metrics(wealth: pd.Series | np.ndarray) -> dict[str, float]:
    """Compute DBF components from a positive wealth or adjusted-price path."""

    values = np.asarray(wealth, dtype=float)
    if values.ndim != 1 or values.size < 2 or not np.isfinite(values).all():
        raise ValueError("wealth must contain at least two finite observations")
    if np.any(values <= 0):
        raise ValueError("wealth observations must be strictly positive")
    return dbf_from_log_returns(np.diff(np.log(values)))
