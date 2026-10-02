"""
STEP 5 - Lifetime value (LTV): does the nudge make money?

We observe 6 months of post-experiment data, but the business question is
about value over 24 months. The model:

  LTV_user = (discounted value observed in months 1-6)
           + (projected value for months 7-24)

  projected value = sum_{k=7..24} r^(k-6) * d_k * v_k
    v_k    : expected monthly value at month k. For customers who already
             pay their salary in, v_k = v_user (their average in months 4-6).
             For customers who don't yet, v_k = v_user + dv * P(switch by k),
             because some of them will still move their salary in later.
             Ignoring this would OVERSTATE the treatment effect: control has
             more customers left who could still switch, so the gap narrows.
    dv     : value uplift when a customer moves their salary in, estimated
             WITHIN customer (control customers who switched in months 2-3:
             months 4-6 value minus month 1 value), avoiding selection bias
    h      : monthly late-switch rate among non-switchers (months 2-6)
    r      : monthly retention for their segment and arm (months 4-6)
    d_k    : discount factor at month k (10% a year)

Then we compare treatment vs control LTV per segment (Welch CI, Holm
correction) and turn the result into a launch decision in pounds.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis_utils as U
import config as C

PER_N_CUSTOMERS = 100_000   # express the business case per 100k eligible customers


def main():
    U.set_style()
    users = U.query("select user_id, segment, is_treatment from fct_experiment_users")
    monthly = U.query("""
        select user_id, month_number, net_value, closed_end_of_month, has_salary_deposit
        from fct_user_monthly_value
    """)
    print(f"Loaded {len(users):,} customers and {len(monthly):,} customer-months")

    disc = {m: C.monthly_discount(m) for m in range(1, C.LTV_HORIZON_MONTHS + 1)}
    monthly["disc_value"] = monthly.net_value * monthly.month_number.map(disc)
    monthly = monthly.merge(users, on="user_id")

    # ---- observed discounted value, months 1-6 ---------------------------------
    observed = monthly.groupby("user_id").disc_value.sum().rename("value_observed")

    # ---- retention: survival curves and steady-state monthly retention --------
    n_assigned = users.groupby(["segment", "is_treatment"]).size().rename("n_assigned")
    active = monthly.groupby(["segment", "is_treatment", "month_number"]).size().rename("n_active")
    surv = active.reset_index().merge(n_assigned.reset_index(), on=["segment", "is_treatment"])
    surv["survival"] = surv.n_active / surv.n_assigned
    surv.to_csv(C.TABLE_DIR / "survival_by_segment.csv", index=False)

    last = monthly[monthly.month_number == C.OBSERVED_MONTHS]
    open_after = last[last.closed_end_of_month == 0].groupby(["segment", "is_treatment"]).size()
    active_m4 = active.xs(4, level="month_number")
    retention = ((open_after / active_m4) ** (1 / 3)).rename("monthly_retention")
    print("\nMonthly retention (months 4-6):")
    print(retention.unstack().round(4).to_string())

    # ---- late salary switching: rate h and value uplift dv --------------------
    sal = monthly.pivot_table(index="user_id", columns="month_number",
                              values="has_salary_deposit", aggfunc="max")
    seg_of = users.set_index("user_id")
    h_rows, dv_rows = [], []
    for (seg, t), ids in users.groupby(["segment", "is_treatment"]).user_id:
        s_ = sal.loc[sal.index.intersection(ids)]
        at_risk = new = 0
        for m in range(2, C.OBSERVED_MONTHS + 1):
            prev, cur = s_[m - 1], s_[m]
            ok = prev.notna() & cur.notna() & (prev == 0)
            at_risk += ok.sum()
            new += (ok & (cur == 1)).sum()
        h_rows.append({"segment": seg, "is_treatment": t, "late_switch_rate": new / at_risk})
    late_switch = pd.DataFrame(h_rows).set_index(["segment", "is_treatment"]).late_switch_rate

    ctrl_ids = users[users.is_treatment == 0].user_id
    s_c = sal.loc[sal.index.intersection(ctrl_ids)]
    switchers = s_c[(s_c[1] == 0) & ((s_c[2] == 1) | (s_c[3] == 1)) & s_c[6].notna()].index
    v_m1 = monthly[(monthly.month_number == 1)].set_index("user_id").net_value
    v_46 = monthly[monthly.month_number >= 4].groupby("user_id").net_value.mean()
    sw = pd.DataFrame({"dv": v_46.reindex(switchers) - v_m1.reindex(switchers)})
    sw["segment"] = seg_of.loc[switchers, "segment"].values
    dv = sw.groupby("segment").dv.mean()
    print("\nLate salary switching (months 2-6) and within-customer value uplift:")
    print(pd.DataFrame({"late_switch_rate_control": late_switch.xs(0, level="is_treatment"),
                        "late_switch_rate_treatment": late_switch.xs(1, level="is_treatment"),
                        "dv_per_month": dv}).round(4).to_string())

    # ---- projected tail value, months 7-24 -------------------------------------
    late = monthly[monthly.month_number >= 4]
    v_user = late.groupby("user_id").net_value.mean().rename("v_user")
    still_open = last.loc[last.closed_end_of_month == 0,
                          ["user_id", "segment", "is_treatment", "has_salary_deposit"]]
    still_open = still_open.merge(v_user, on="user_id")
    k = np.arange(C.OBSERVED_MONTHS + 1, C.LTV_HORIZON_MONTHS + 1)
    d_k = np.array([disc[m] for m in k])
    proj = np.zeros(len(still_open))
    for (seg, t), idx in still_open.groupby(["segment", "is_treatment"]).groups.items():
        r, h = retention[(seg, t)], late_switch[(seg, t)]
        surv_k = r ** (k - C.OBSERVED_MONTHS)
        p_switch_k = 1 - (1 - h) ** (k - C.OBSERVED_MONTHS)
        g = still_open.loc[idx]
        base = g.v_user.values * np.sum(surv_k * d_k)
        extra = np.where(g.has_salary_deposit.values == 0, dv[seg] * np.sum(surv_k * d_k * p_switch_k), 0.0)
        proj[still_open.index.get_indexer(idx)] = base + extra
    still_open["value_projected"] = proj

    ltv = users.merge(observed, on="user_id", how="left") \
               .merge(still_open[["user_id", "value_projected"]], on="user_id", how="left")
    ltv = ltv.fillna({"value_observed": 0.0, "value_projected": 0.0})
    ltv["ltv24"] = ltv.value_observed + ltv.value_projected
    ltv[["user_id", "segment", "is_treatment", "value_observed", "ltv24"]] \
        .to_csv(C.TABLE_DIR / "user_ltv.csv.gz", index=False, compression="gzip")

    # ---- treatment effect on LTV, by segment -----------------------------------
    rows = []
    for seg in C.SEGMENT_ORDER + ["all"]:
        g = ltv if seg == "all" else ltv[ltv.segment == seg]
        r24 = U.diff_in_means(g.loc[g.is_treatment == 1, "ltv24"], g.loc[g.is_treatment == 0, "ltv24"])
        r6 = U.diff_in_means(g.loc[g.is_treatment == 1, "value_observed"],
                             g.loc[g.is_treatment == 0, "value_observed"])
        rows.append({"segment": seg, "label": C.SEGMENT_LABELS.get(seg, "All customers"),
                     "share": len(g) / len(ltv), "n": len(g),
                     "ltv_control": r24["mean_control"], "ltv_treatment": r24["mean_treatment"],
                     "ltv_diff": r24["diff"], "ltv_se": r24["se"], "ltv_ci_low": r24["ci_low"],
                     "ltv_ci_high": r24["ci_high"], "ltv_p": r24["p_value"],
                     "value6_diff": r6["diff"], "value6_ci_low": r6["ci_low"], "value6_ci_high": r6["ci_high"]})
    table = pd.DataFrame(rows)
    seg_mask = table.segment != "all"
    table.loc[seg_mask, "ltv_p_holm"] = U.holm(table.loc[seg_mask, "ltv_p"])

    # Decision rule (pre-registered): launch to a segment only if its LTV effect
    # is significantly positive after Holm correction.
    table["launch"] = seg_mask & (table.ltv_p_holm < C.ALPHA) & (table.ltv_diff > 0)
    table.to_csv(C.TABLE_DIR / "ltv_by_segment.csv", index=False)
    print("\n24-month LTV effect by segment:")
    for r in table.itertuples():
        print(f"  {r.label:<20} control £{r.ltv_control:7.2f}  treatment £{r.ltv_treatment:7.2f}  "
              f"diff £{r.ltv_diff:+.2f} [{r.ltv_ci_low:+.2f}, {r.ltv_ci_high:+.2f}]  "
              f"6m diff £{r.value6_diff:+.2f}  launch={r.launch}")

    # ---- business case per 100k eligible customers -----------------------------
    seg_rows = table[seg_mask]
    full_value = (seg_rows.share * seg_rows.ltv_diff).sum() * PER_N_CUSTOMERS
    full_se = np.sqrt(((seg_rows.share * PER_N_CUSTOMERS * seg_rows.ltv_se) ** 2).sum())
    tgt = seg_rows[seg_rows.launch]
    tgt_value = (tgt.share * tgt.ltv_diff).sum() * PER_N_CUSTOMERS
    tgt_se = np.sqrt(((tgt.share * PER_N_CUSTOMERS * tgt.ltv_se) ** 2).sum())
    business = {
        "per_n_customers": PER_N_CUSTOMERS,
        "full_launch_value": full_value, "full_launch_ci": [full_value - 1.96 * full_se, full_value + 1.96 * full_se],
        "targeted_launch_value": tgt_value, "targeted_launch_ci": [tgt_value - 1.96 * tgt_se, tgt_value + 1.96 * tgt_se],
        "targeted_segments": tgt.segment.tolist(),
        "targeted_share_of_customers": float(tgt.share.sum()),
        "uplift_targeted_vs_full": tgt_value - full_value,
    }
    print(f"\nPer {PER_N_CUSTOMERS:,} eligible customers (24-month value):")
    print(f"  launch to everyone : £{full_value:,.0f}  95% CI [£{business['full_launch_ci'][0]:,.0f}, £{business['full_launch_ci'][1]:,.0f}]")
    print(f"  targeted launch    : £{tgt_value:,.0f}  95% CI [£{business['targeted_launch_ci'][0]:,.0f}, £{business['targeted_launch_ci'][1]:,.0f}]")

    U.save_json({"retention": {f"{s}|{t}": v for (s, t), v in retention.items()},
                 "late_switch_rate": {f"{s}|{t}": v for (s, t), v in late_switch.items()},
                 "dv_per_month": dv.to_dict(),
                 "ltv_by_segment": table.to_dict(orient="records"),
                 "business_case": business}, "ltv_model.json")

    # ---- figures ----------------------------------------------------------------
    seg_tbl = table[seg_mask].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ypos = np.arange(len(seg_tbl))[::-1]
    for y_, r in zip(ypos, seg_tbl.itertuples()):
        color = U.TREATMENT if r.launch else U.NEGATIVE
        ax.errorbar(r.ltv_diff, y_, xerr=[[r.ltv_diff - r.ltv_ci_low], [r.ltv_ci_high - r.ltv_diff]],
                    fmt="o", color=color, capsize=4, ms=7, lw=2)
        label = f"+£{r.ltv_diff:.2f}" if r.ltv_diff >= 0 else f"−£{abs(r.ltv_diff):.2f}"
        if r.ltv_diff >= 0:
            ax.text(r.ltv_ci_high + 0.3, y_, label, va="center", ha="left", fontsize=9, color=U.INK)
        else:
            ax.text(r.ltv_ci_low - 0.3, y_, label, va="center", ha="right", fontsize=9, color=U.INK)
    ax.axvline(0, color=U.INK, lw=1)
    ax.set_yticks(ypos, seg_tbl.label)
    ax.set_xlabel("Change in 24-month value per customer (£, 95% CI)")
    ax.set_title("The nudge creates value for salaried customers only")
    ax.set_xlim(min(seg_tbl.ltv_ci_low) - 2.5, max(seg_tbl.ltv_ci_high) + 2.5)
    fig.savefig(C.FIG_DIR / "06_ltv_by_segment.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 4, figsize=(11, 3), sharey=True)
    for ax, seg in zip(axes, C.SEGMENT_ORDER):
        for t, color, lab in [(0, U.CONTROL, "Control"), (1, U.TREATMENT, "Treatment")]:
            s = surv[(surv.segment == seg) & (surv.is_treatment == t)].sort_values("month_number")
            r = retention[(seg, t)]
            proj_m = np.arange(C.OBSERVED_MONTHS, C.LTV_HORIZON_MONTHS + 1)
            last_s = s.survival.iloc[-1] * r  # open after month 6
            proj = last_s * r ** (proj_m - C.OBSERVED_MONTHS)
            ax.plot(s.month_number, s.survival * 100, color=color, lw=2, label=lab)
            ax.plot(proj_m + 1, proj * 100, color=color, lw=1.5, ls="--")
        ax.set_title(C.SEGMENT_LABELS[seg], fontsize=10)
        ax.set_xlabel("Month")
        ax.axvspan(C.OBSERVED_MONTHS + 0.5, C.LTV_HORIZON_MONTHS + 1, color=U.GRID, alpha=0.35, lw=0)
    axes[0].set_ylabel("Accounts still open (%)")
    axes[0].legend(loc="lower left", fontsize=8)
    fig.suptitle("Retention: observed months 1-6 (solid), projected months 7-24 (dashed, shaded)",
                 x=0.01, y=1.06, ha="left", fontweight="bold", color=U.INK)
    fig.savefig(C.FIG_DIR / "07_retention_curves.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    labels = ["Launch to everyone", "Targeted launch\n(salaried only)"]
    vals = [full_value, tgt_value]
    cis = [business["full_launch_ci"], business["targeted_launch_ci"]]
    colors = [U.CONTROL, U.TREATMENT]
    ax.barh(labels[::-1], [v / 1000 for v in vals[::-1]], color=colors[::-1], height=0.5,
            xerr=[[(v - c[0]) / 1000 for v, c in zip(vals[::-1], cis[::-1])],
                  [(c[1] - v) / 1000 for v, c in zip(vals[::-1], cis[::-1])]],
            error_kw=dict(ecolor=U.INK, capsize=4, lw=1.2))
    for i, (v, c) in enumerate(zip(vals[::-1], cis[::-1])):
        ax.text(c[1] / 1000 + 12, i, f"£{v / 1000:,.0f}k", va="center", fontsize=10, color=U.INK, fontweight="bold")
    ax.set_xlabel(f"Incremental 24-month value per {PER_N_CUSTOMERS:,} eligible customers (£k)")
    ax.set_title("Targeting beats a full launch")
    ax.set_xlim(0, max(c[1] for c in cis) / 1000 * 1.25)
    fig.savefig(C.FIG_DIR / "08_business_case.png")
    plt.close(fig)
    print("Saved results, tables and figures.")


if __name__ == "__main__":
    main()
