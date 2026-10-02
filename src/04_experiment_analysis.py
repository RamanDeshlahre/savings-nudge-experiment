"""
STEP 4 - Analyse the experiment.

Order matters, and mirrors how you'd do it at work:
  4a. Health check first: sample ratio mismatch (SRM). If the split is wrong,
      nothing downstream can be trusted until we know why.
  4b. Primary metric, intention-to-treat (ITT), with and without CUPED.
  4c. Secondary metrics and guardrails against pre-registered thresholds.
  4d. Segment effects (heterogeneity), with Holm correction for multiple tests.
  4e. Novelty effect: does the lift fade week by week?
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis_utils as U
import config as C


def srm_section(df):
    print("\n4a. Sample ratio mismatch")
    out = {}

    # What a naive analyst would use: users with a logged exposure event
    logged = df[df.exposure_logged == 1]
    out["exposure_logs"] = U.srm_test((logged.variant == "treatment").sum(),
                                      (logged.variant == "control").sum())
    # Source of truth: server-side assignment
    out["server_assignments"] = U.srm_test((df.variant == "treatment").sum(),
                                           (df.variant == "control").sum())
    for k in ["exposure_logs", "server_assignments"]:
        r = out[k]
        print(f"  {k:<20} treatment share {r['share_a']:.4f}  chi2={r['chi2']:8.1f}  p={r['p_value']:.2e}")

    # Drill down: where is the mismatch coming from?
    rows = []
    for (plat, ver), g in df.groupby(["platform", "app_version"]):
        lg = g[g.exposure_logged == 1]
        r = U.srm_test((lg.variant == "treatment").sum(), (lg.variant == "control").sum())
        rows.append({"platform": plat, "app_version": ver, "logged_users": len(lg),
                     "treatment_share": r["share_a"], "p_value": r["p_value"]})
    drill = pd.DataFrame(rows)
    drill.to_csv(C.TABLE_DIR / "srm_drilldown.csv", index=False)
    print(drill.to_string(index=False))
    out["drilldown"] = drill.to_dict(orient="records")

    # Naive (exposure-based) vs ITT estimate of the primary metric
    naive = U.diff_in_means(logged.loc[logged.is_treatment == 1, "salary_switched_30d"],
                            logged.loc[logged.is_treatment == 0, "salary_switched_30d"])
    out["naive_primary"] = naive
    print(f"  naive primary-metric lift (exposure logs): {naive['diff'] * 100:.2f}pp")

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    labels = [f"{r.platform}\n{r.app_version}" for r in drill.itertuples()]
    colors = [U.NEGATIVE if r.p_value < 0.001 else U.CONTROL for r in drill.itertuples()]
    ax.bar(labels, drill.treatment_share * 100, color=colors, width=0.55)
    ax.axhline(50, color=U.INK, lw=1, ls="--")
    ax.set_ylim(0, 58)
    ax.set_ylabel("Treatment share of logged users (%)")
    ax.set_title("Exposure logs lose treatment users on legacy Android")
    for i, r in enumerate(drill.itertuples()):
        ax.text(i, r.treatment_share * 100 + 1.0, f"{r.treatment_share * 100:.1f}%",
                ha="center", color=U.INK, fontsize=9)
    fig.savefig(C.FIG_DIR / "02_srm_drilldown.png")
    plt.close(fig)
    return out


def primary_section(df):
    print("\n4b. Primary metric: salary moved in within 30 days (ITT)")
    t = df.is_treatment.values
    y = df.salary_switched_30d.values
    # Pre-period covariate: log spend + transaction count capture engagement
    x = np.log1p(df.pre_card_spend.values) + 0.02 * df.pre_txn_count.values
    raw, adj = U.cuped(y, x, t)
    print(f"  raw   : {raw['mean_control']:.4f} -> {raw['mean_treatment']:.4f}  "
          f"diff {raw['diff'] * 100:.2f}pp [{raw['ci_low'] * 100:.2f}, {raw['ci_high'] * 100:.2f}]  p={raw['p_value']:.1e}")
    print(f"  CUPED : diff {adj['diff'] * 100:.2f}pp [{adj['ci_low'] * 100:.2f}, {adj['ci_high'] * 100:.2f}]  "
          f"variance reduction {adj['variance_reduction']:.1%}")
    return {"raw": raw, "cuped": adj}


def secondary_section(df):
    print("\n4c. Secondary metrics and guardrails")
    t = df.is_treatment.values
    metrics = [
        ("pot_created_30d", "Savings pot opened (30d)", "secondary", None),
        ("salary_switched_6m", "Salary moved in (6 months)", "secondary", None),
        ("card_spend_m1", "Card spend, month 1 (£)", "secondary", "pre_card_spend"),
        ("savings_balance_m1", "Savings balance, month 1 (£)", "secondary", "pre_avg_balance"),
        ("support_contacts_m1", "Support contacts per user, month 1", "guardrail", None),
        ("closed_m1", "Account closed in month 1", "guardrail", None),
        ("active_m6", "Account still open at month 6", "secondary", None),
    ]
    rows = []
    for col, label, kind, cov in metrics:
        y = df[col].values
        if cov:
            raw, res = U.cuped(y, df[cov].values, t)
            vr = res["variance_reduction"]
        else:
            res, vr = U.diff_in_means(y[t == 1], y[t == 0]), 0.0
        rows.append({"metric": col, "label": label, "type": kind, "cuped_variance_reduction": vr,
                     **{k: res[k] for k in ["mean_control", "mean_treatment", "diff",
                                            "ci_low", "ci_high", "p_value", "rel_lift"]}})
    table = pd.DataFrame(rows)

    thresholds = {"support_contacts_m1": C.GUARDRAIL_MAX_SUPPORT_INCREASE,
                  "closed_m1": C.GUARDRAIL_MAX_CLOSURE_INCREASE}
    table["guardrail_threshold"] = table.metric.map(thresholds)
    table["guardrail_pass"] = np.where(table.type == "guardrail",
                                       table.ci_high < table.guardrail_threshold, np.nan)
    table.to_csv(C.TABLE_DIR / "secondary_and_guardrails.csv", index=False)
    with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
        print(table[["label", "mean_control", "mean_treatment", "diff", "ci_low", "ci_high",
                     "cuped_variance_reduction", "guardrail_pass"]].to_string(index=False))
    return table


def segment_section(df):
    print("\n4d. Primary metric by segment (Holm-adjusted)")
    rows = []
    for seg in C.SEGMENT_ORDER:
        g = df[df.segment == seg]
        r = U.diff_in_means(g.loc[g.is_treatment == 1, "salary_switched_30d"],
                            g.loc[g.is_treatment == 0, "salary_switched_30d"])
        rows.append({"segment": seg, "label": C.SEGMENT_LABELS[seg], "n": len(g), **r})
    table = pd.DataFrame(rows)
    table["p_holm"] = U.holm(table.p_value)
    table.to_csv(C.TABLE_DIR / "primary_by_segment.csv", index=False)
    for r in table.itertuples():
        print(f"  {r.label:<20} n={r.n:>7,}  {r.mean_control:.3f} -> {r.mean_treatment:.3f}  "
              f"diff {r.diff * 100:+.2f}pp [{r.ci_low * 100:+.2f}, {r.ci_high * 100:+.2f}]  p_holm={r.p_holm:.1e}")

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ypos = np.arange(len(table))[::-1]
    for y_, r in zip(ypos, table.itertuples()):
        color = U.TREATMENT if r.p_holm < C.ALPHA and r.diff > 0 else U.CONTROL
        ax.errorbar(r.diff * 100, y_, xerr=[[(r.diff - r.ci_low) * 100], [(r.ci_high - r.diff) * 100]],
                    fmt="o", color=color, capsize=4, ms=7, lw=2)
        ax.text(r.ci_high * 100 + 0.3, y_, f"{r.diff * 100:+.1f}pp", va="center", color=U.INK, fontsize=9)
    ax.axvline(0, color=U.INK, lw=1)
    ax.set_yticks(ypos, table.label)
    ax.set_xlabel("Lift in 30-day salary switch rate (percentage points, 95% CI)")
    ax.set_title("The nudge moves salaries for salaried customers, not students")
    ax.set_xlim(-1.5, max(table.ci_high * 100) + 2.5)
    fig.savefig(C.FIG_DIR / "03_primary_by_segment.png")
    plt.close(fig)
    return table


def novelty_section():
    print("\n4e. Novelty effect in weekly pot transfers")
    w = U.query("select * from agg_weekly_pot_transfers order by week_number, variant")
    rows = []
    for week, g in w.groupby("week_number"):
        t = g[g.variant == "treatment"].iloc[0]
        c = g[g.variant == "control"].iloc[0]
        def mean_var(r):
            m = r.total_transfers / r.n_assigned
            return m, r.sum_sq_transfers / r.n_assigned - m ** 2
        m_t, v_t = mean_var(t)
        m_c, v_c = mean_var(c)
        se = np.sqrt(v_t / t.n_assigned + v_c / c.n_assigned)
        rows.append({"week": week, "control": m_c, "treatment": m_t, "diff": m_t - m_c,
                     "ci_low": m_t - m_c - 1.96 * se, "ci_high": m_t - m_c + 1.96 * se,
                     "rel_lift": (m_t - m_c) / m_c})
    table = pd.DataFrame(rows)
    table.to_csv(C.TABLE_DIR / "novelty_weekly.csv", index=False)
    print(table.round(4).to_string(index=False))

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.plot(table.week, table.rel_lift * 100, color=U.TREATMENT, marker="o", lw=2.2)
    ax.fill_between(table.week, table.ci_low / table.control * 100, table.ci_high / table.control * 100,
                    color=U.TREATMENT, alpha=0.15, lw=0)
    ax.set_xlabel("Week since the nudge was shown")
    ax.set_ylabel("Lift in pot transfers per user (%)")
    ax.set_title("Novelty effect: week-1 lift fades to a smaller lasting one")
    ax.set_ylim(0, None)
    fig.savefig(C.FIG_DIR / "04_novelty_effect.png")
    plt.close(fig)
    return table


def main():
    U.set_style()
    df = U.query("select * from fct_experiment_users")
    print(f"Loaded {len(df):,} randomised customers")

    srm = srm_section(df)
    primary = primary_section(df)
    secondary = secondary_section(df)
    segments = segment_section(df)
    novelty = novelty_section()

    # Figure: naive vs ITT vs CUPED for the primary metric
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    est = [("Naive: exposure logs", srm["naive_primary"], U.NEGATIVE),
           ("ITT: server assignments", primary["raw"], U.CONTROL),
           ("ITT + CUPED", primary["cuped"], U.TREATMENT)]
    for i, (label, r, color) in enumerate(est[::-1]):
        ax.errorbar(r["diff"] * 100, i, xerr=[[(r["diff"] - r["ci_low"]) * 100], [(r["ci_high"] - r["diff"]) * 100]],
                    fmt="o", color=color, capsize=4, ms=7, lw=2)
        ax.text(r["ci_high"] * 100 + 0.02, i, f"{r['diff'] * 100:.2f}pp", va="center", fontsize=9, color=U.INK)
    ax.set_yticks(range(3), [e[0] for e in est[::-1]])
    ax.set_xlim(min(e[1]["ci_low"] for e in est) * 100 - 0.05, max(e[1]["ci_high"] for e in est) * 100 + 0.15)
    ax.set_ylim(-0.6, 2.6)
    ax.set_xlabel("Lift in 30-day salary switch rate (pp, 95% CI)")
    ax.set_title("Primary metric: the naive estimate is inflated")
    fig.savefig(C.FIG_DIR / "05_primary_estimates.png")
    plt.close(fig)

    U.save_json({
        "srm": {k: v for k, v in srm.items()},
        "primary": primary,
        "secondary": secondary.to_dict(orient="records"),
        "segments": segments.to_dict(orient="records"),
        "novelty": novelty.to_dict(orient="records"),
    }, "experiment_analysis.json")
    print("\nSaved results, tables and figures.")


if __name__ == "__main__":
    main()
