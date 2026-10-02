"""
STEP 3 - Power analysis (done BEFORE looking at results).

Question: how many customers do we need?

The key insight: the primary metric (salary switch rate) needs only ~15k
customers per arm. But the decision depends on LIFETIME VALUE per SEGMENT,
which is far noisier. Sizing for the hardest question we must answer
(LTV in the smallest segment) is what justifies ~1M customers.

Inputs are "historical" planning assumptions, written into the
pre-registration (docs/pre_registration.md) before launch.
"""
import matplotlib.pyplot as plt
import numpy as np

import analysis_utils as U
import config as C

# Planning assumptions (from historical cohorts, before the experiment)
BASELINE_SALARY_RATE = 0.10       # ~10% of eligible customers move salary within 30 days
MDE_SALARY_ABS = 0.01             # want to detect +1 percentage point
LTV_SD = 100.0                    # SD of 24-month customer value, £ (heavy-tailed)
MDE_LTV = 1.50                    # want to detect £1.50 per customer within a segment
SMALLEST_SEGMENT_SHARE = 0.15     # self-employed are ~15% of eligible customers


def main():
    U.set_style()
    n_primary = U.n_per_arm_proportion(BASELINE_SALARY_RATE, MDE_SALARY_ABS)
    n_ltv_overall = U.n_per_arm_mean(LTV_SD, MDE_LTV)
    n_ltv_segment_total = int(np.ceil(2 * n_ltv_overall / SMALLEST_SEGMENT_SHARE))

    results = {
        "assumptions": {
            "baseline_salary_rate": BASELINE_SALARY_RATE, "mde_salary_abs": MDE_SALARY_ABS,
            "ltv_sd": LTV_SD, "mde_ltv": MDE_LTV, "smallest_segment_share": SMALLEST_SEGMENT_SHARE,
            "alpha": C.ALPHA, "power": C.POWER,
        },
        "n_per_arm_primary": n_primary,
        "n_total_primary": 2 * n_primary,
        "n_per_arm_ltv_per_segment": n_ltv_overall,
        "n_total_for_segment_ltv": n_ltv_segment_total,
        "n_planned": C.N_USERS,
    }
    U.save_json(results, "power_analysis.json")

    print(f"Primary metric (+{MDE_SALARY_ABS:.0%} on {BASELINE_SALARY_RATE:.0%}): "
          f"{n_primary:,} per arm ({2 * n_primary:,} total)")
    print(f"LTV (£{MDE_LTV} with SD £{LTV_SD}) within the smallest segment: "
          f"{n_ltv_overall:,} per arm -> {n_ltv_segment_total:,} customers in total")
    print(f"Planned sample: {C.N_USERS:,}")

    # Power curve: power to detect an LTV difference in the smallest segment
    mdes = np.linspace(0.25, 4, 200)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for total, color, label in [(100_000, U.CONTROL, "100k customers"),
                                (400_000, U.WARNING, "400k customers"),
                                (C.N_USERS, U.TREATMENT, "1M customers (planned)")]:
        n_arm = total * SMALLEST_SEGMENT_SHARE / 2
        ax.plot(mdes, U.power_for_n(n_arm, LTV_SD, mdes), color=color, lw=2.2, label=label)
    ax.axhline(C.POWER, color=U.MUTED, ls="--", lw=1)
    ax.axvline(MDE_LTV, color=U.MUTED, ls=":", lw=1)
    ax.text(MDE_LTV + 0.05, 0.05, f"target MDE £{MDE_LTV:.2f}", color=U.MUTED, fontsize=9)
    ax.set_xlabel("True difference in 24-month value per customer (£)")
    ax.set_ylabel("Power")
    ax.set_title("Sample size is driven by LTV in the smallest segment")
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right")
    fig.savefig(C.FIG_DIR / "01_power_curve.png")
    print("Saved outputs/figures/01_power_curve.png")


if __name__ == "__main__":
    main()
