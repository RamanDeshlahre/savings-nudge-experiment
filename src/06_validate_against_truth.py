"""
STEP 6 - Method validation against the planted ground truth.

This is the payoff of simulating: we know the TRUE effect for every customer
(both potential outcomes), so we can check whether our methods recover it.

We separate two sources of error:
  * sampling + design error  -> checked with 6-month value and the primary
    metric (no modelling involved; CIs should contain the truth ~95% of the time)
  * projection (model) error  -> the 24-month LTV adds a model on top, so any
    extra gap is the price of extrapolating from 6 months of data
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis_utils as U
import config as C


def main():
    U.set_style()
    truth = pd.read_csv(C.TRUTH_DIR / "potential_outcomes.csv")
    truth["d_salary"] = truth.salary30_treatment - truth.salary30_control
    truth["d_value6"] = truth.value6_treatment - truth.value6_control
    truth["d_ltv24"] = truth.ltv24_treatment - truth.ltv24_control

    exp = U.load_json("experiment_analysis.json")
    ltv = pd.DataFrame(U.load_json("ltv_model.json")["ltv_by_segment"])
    seg_primary = pd.DataFrame(exp["segments"])
    business = U.load_json("ltv_model.json")["business_case"]

    rows = []
    # Primary metric, overall: naive vs ITT vs CUPED
    true_overall = truth.d_salary.mean()
    for name, r in [("Primary, naive (exposure logs)", exp["srm"]["naive_primary"]),
                    ("Primary, ITT", exp["primary"]["raw"]),
                    ("Primary, ITT + CUPED", exp["primary"]["cuped"])]:
        rows.append({"check": name, "segment": "all", "estimate": r["diff"], "ci_low": r["ci_low"],
                     "ci_high": r["ci_high"], "truth": true_overall})
    # Primary metric by segment
    for r in seg_primary.itertuples():
        rows.append({"check": "Primary by segment", "segment": r.segment, "estimate": r.diff,
                     "ci_low": r.ci_low, "ci_high": r.ci_high,
                     "truth": truth.loc[truth.segment == r.segment, "d_salary"].mean()})
    # 6-month value (observed, no model) and 24-month LTV (modelled)
    for r in ltv.itertuples():
        t = truth if r.segment == "all" else truth[truth.segment == r.segment]
        rows.append({"check": "6-month value (observed)", "segment": r.segment, "estimate": r.value6_diff,
                     "ci_low": r.value6_ci_low, "ci_high": r.value6_ci_high, "truth": t.d_value6.mean()})
        rows.append({"check": "24-month LTV (projected)", "segment": r.segment, "estimate": r.ltv_diff,
                     "ci_low": r.ltv_ci_low, "ci_high": r.ltv_ci_high, "truth": t.d_ltv24.mean()})

    table = pd.DataFrame(rows)
    table["error"] = table.estimate - table.truth
    table["ci_covers_truth"] = (table.ci_low <= table.truth) & (table.truth <= table.ci_high)
    table.to_csv(C.TABLE_DIR / "validation_vs_truth.csv", index=False)
    with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
        print(table.to_string(index=False))

    # Did we make the right decision? Compare to the decision the truth implies.
    true_by_seg = truth.groupby("segment").d_ltv24.mean()
    shares = truth.segment.value_counts(normalize=True)
    true_targeted = sum(shares[s] * true_by_seg[s] for s in business["targeted_segments"]) * business["per_n_customers"]
    true_full = truth.d_ltv24.mean() * business["per_n_customers"]
    true_launch_set = sorted(true_by_seg[true_by_seg > 0].index)
    decision = {
        "estimated_launch_segments": sorted(business["targeted_segments"]),
        "true_positive_segments": true_launch_set,
        "decision_correct": sorted(business["targeted_segments"]) == true_launch_set,
        "true_targeted_value": true_targeted, "estimated_targeted_value": business["targeted_launch_value"],
        "true_full_value": true_full, "estimated_full_value": business["full_launch_value"],
    }
    print("\nDecision check:", decision)

    U.save_json({"checks": table.to_dict(orient="records"), "decision": decision}, "validation.json")

    # Figure: LTV estimates vs truth (observed 6m and projected 24m)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, check, title in [(axes[0], "6-month value (observed)", "6-month value: no model, CIs cover the truth"),
                             (axes[1], "24-month LTV (projected)", "24-month LTV: projection adds some error")]:
        sub = table[(table.check == check) & (table.segment != "all")].reset_index(drop=True)
        ypos = np.arange(len(sub))[::-1]
        for y_, r in zip(ypos, sub.itertuples()):
            ax.errorbar(r.estimate, y_, xerr=[[r.estimate - r.ci_low], [r.ci_high - r.estimate]],
                        fmt="o", color=U.TREATMENT, capsize=4, ms=6, lw=2,
                        label="Estimate (95% CI)" if y_ == ypos[0] else None)
            ax.plot(r.truth, y_, marker="D", color=U.WARNING, ms=7, ls="none",
                    label="True effect" if y_ == ypos[0] else None)
        ax.axvline(0, color=U.INK, lw=1)
        ax.set_yticks(ypos, [C.SEGMENT_LABELS[s] for s in sub.segment])
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Effect per customer (£)")
    axes[0].legend(loc="lower right", fontsize=8)
    fig.savefig(C.FIG_DIR / "09_validation_vs_truth.png")
    plt.close(fig)
    print("Saved outputs/figures/09_validation_vs_truth.png")


if __name__ == "__main__":
    main()
