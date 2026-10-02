"""
Shared statistics and plotting helpers.

Every function here is small and written out explicitly (no black-box
experimentation library), so each formula can be explained in an interview.
"""
import json
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import config as C

# ---------------------------------------------------------------------------
# Plot style (one palette across every chart)
# ---------------------------------------------------------------------------
INK = "#1C2333"
MUTED = "#6B7385"
GRID = "#E3E6EC"
CONTROL = "#8A94A6"
TREATMENT = "#0F7B6C"
NEGATIVE = "#B4432F"
WARNING = "#C98A12"


def set_style():
    plt.rcParams.update({
        "figure.dpi": 130, "savefig.dpi": 130, "savefig.bbox": "tight",
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.edgecolor": GRID, "axes.labelcolor": INK, "axes.titlecolor": INK,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    })


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
def query(sql: str) -> pd.DataFrame:
    with sqlite3.connect(C.WAREHOUSE) as con:
        return pd.read_sql_query(sql, con)


def save_json(obj, name):
    C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(C.RESULTS_DIR / name, "w") as f:
        json.dump(obj, f, indent=2, default=float)


def load_json(name):
    with open(C.RESULTS_DIR / name) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Core statistics
# ---------------------------------------------------------------------------
def diff_in_means(y_t, y_c, alpha=C.ALPHA):
    """Welch difference in means (works for 0/1 metrics too: it's then a
    difference in proportions with unpooled standard error)."""
    y_t, y_c = np.asarray(y_t, float), np.asarray(y_c, float)
    m_t, m_c = y_t.mean(), y_c.mean()
    v_t, v_c = y_t.var(ddof=1), y_c.var(ddof=1)
    se = np.sqrt(v_t / len(y_t) + v_c / len(y_c))
    diff = m_t - m_c
    z = stats.norm.ppf(1 - alpha / 2)
    p = 2 * (1 - stats.norm.cdf(abs(diff / se)))
    return {
        "mean_control": m_c, "mean_treatment": m_t, "diff": diff, "se": se,
        "ci_low": diff - z * se, "ci_high": diff + z * se, "p_value": p,
        "rel_lift": diff / m_c if m_c != 0 else np.nan,
        "n_control": len(y_c), "n_treatment": len(y_t),
    }


def cuped(y, x, treat):
    """CUPED: y_adj = y - theta * (x - mean(x)), theta = cov(y, x) / var(x).
    theta is estimated on the pooled sample (both arms). Because x is measured
    BEFORE the experiment it is independent of treatment, so the estimate stays
    unbiased while the variance drops by roughly corr(x, y)^2."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    theta = np.cov(y, x, ddof=1)[0, 1] / x.var(ddof=1)
    y_adj = y - theta * (x - x.mean())
    raw = diff_in_means(y[treat == 1], y[treat == 0])
    adj = diff_in_means(y_adj[treat == 1], y_adj[treat == 0])
    adj["theta"] = theta
    adj["variance_reduction"] = 1 - (adj["se"] / raw["se"]) ** 2
    adj["corr_xy"] = np.corrcoef(x, y)[0, 1]
    return raw, adj


def srm_test(n_a, n_b, expected_share_a=0.5):
    """Chi-square goodness-of-fit test for sample ratio mismatch."""
    total = n_a + n_b
    expected = np.array([total * expected_share_a, total * (1 - expected_share_a)])
    chi2, p = stats.chisquare([n_a, n_b], expected)
    return {"n_a": int(n_a), "n_b": int(n_b), "share_a": n_a / total, "chi2": chi2, "p_value": p}


def holm(p_values):
    """Holm-Bonferroni adjusted p-values (controls family-wise error rate)."""
    p = np.asarray(p_values, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


def n_per_arm_proportion(p_base, mde_abs, alpha=C.ALPHA, power=C.POWER):
    """Sample size per arm for a two-sided test of two proportions."""
    p_alt = p_base + mde_abs
    z_a, z_b = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    var = p_base * (1 - p_base) + p_alt * (1 - p_alt)
    return int(np.ceil((z_a + z_b) ** 2 * var / mde_abs ** 2))


def n_per_arm_mean(sd, mde_abs, alpha=C.ALPHA, power=C.POWER):
    """Sample size per arm for a two-sided test of two means (equal SDs)."""
    z_a, z_b = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return int(np.ceil(2 * (z_a + z_b) ** 2 * sd ** 2 / mde_abs ** 2))


def power_for_n(n_per_arm, sd, mde_abs, alpha=C.ALPHA):
    z_a = stats.norm.ppf(1 - alpha / 2)
    se = sd * np.sqrt(2 / n_per_arm)
    return stats.norm.cdf(mde_abs / se - z_a)
