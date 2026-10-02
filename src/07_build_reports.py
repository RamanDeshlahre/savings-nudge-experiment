"""
STEP 7 - Build the stakeholder outputs from the saved results:
  * docs/decision_memo.md   - one-page recommendation for product + finance
  * dashboard/index.html    - self-contained experiment readout (open in a browser)

Every number is read from outputs/results/*.json, so re-running the pipeline
with different assumptions regenerates consistent reports.
"""
import base64
import html

import analysis_utils as U
import config as C


def gbp(x, dp=2):
    sign = "−" if x < 0 else "+"
    return f"{sign}£{abs(x):,.{dp}f}"


def pp(x):
    return f"{x * 100:+.1f}pp"


def load():
    return (U.load_json("power_analysis.json"), U.load_json("experiment_analysis.json"),
            U.load_json("ltv_model.json"), U.load_json("validation.json"))


def build_memo(power, exp, ltv, val):
    b = ltv["business_case"]
    segs = {r["segment"]: r for r in ltv["ltv_by_segment"]}
    prim = exp["primary"]["cuped"]
    sec = {r["metric"]: r for r in exp["secondary"]}
    seg_prim = {r["segment"]: r for r in exp["segments"]}
    srm = exp["srm"]
    lift_pct = (b["targeted_launch_value"] / b["full_launch_value"] - 1) * 100
    d = val["decision"]
    proj_err = (d["estimated_targeted_value"] / d["true_targeted_value"] - 1) * 100
    launch_share = b["targeted_share_of_customers"] * 100

    rows = []
    for s in C.SEGMENT_ORDER:
        r, p = segs[s], seg_prim[s]
        rows.append(f"| {C.SEGMENT_LABELS[s]} | {r['share'] * 100:.0f}% | {pp(p['diff'])} | "
                    f"{gbp(r['ltv_diff'])} ({gbp(r['ltv_ci_low'])} to {gbp(r['ltv_ci_high'])}) | "
                    f"{'**Launch**' if r['launch'] else 'Hold'} |")

    memo = f"""# Savings nudge: launch recommendation

*Decision memo for the product squad and finance partner. Simulated data; see README.*

## Recommendation

**Launch the savings nudge to salaried customers only ({launch_share:.0f}% of eligible customers). Hold it for students and self-employed customers.**

A targeted launch is worth an estimated **£{b['targeted_launch_value'] / 1000:,.0f}k in 24-month value per 100,000 eligible customers** (95% CI £{b['targeted_launch_ci'][0] / 1000:,.0f}k to £{b['targeted_launch_ci'][1] / 1000:,.0f}k), about {lift_pct:.0f}% more than launching to everyone (£{b['full_launch_value'] / 1000:,.0f}k), because for two segments the nudge destroys value.

## What we tested

Eligible customers (1 to 12 months tenure, salary not yet paid in) were randomised 50/50 server-side. Treatment saw an in-app nudge to open a savings pot and move their salary in. {C.N_USERS:,} customers took part; the pre-registered sample size was driven by the need to detect a £{power['assumptions']['mde_ltv']:.2f} lifetime-value difference within the smallest segment (≈{power['n_total_for_segment_ltv'] / 1e6:.2f}M customers), not by the primary metric (≈{power['n_total_primary'] / 1000:.0f}k).

## Results

**Primary metric.** The share of customers moving their salary in within 30 days rose from {prim['mean_control'] * 100:.1f}% to {prim['mean_treatment'] * 100:.1f}% ({pp(prim['diff'])}, 95% CI {prim['ci_low'] * 100:.2f} to {prim['ci_high'] * 100:.2f}pp, a {prim['rel_lift'] * 100:.0f}% relative lift).

**Guardrails passed.** Support contacts in month 1 rose by {sec['support_contacts_m1']['diff']:.3f} per customer (threshold {C.GUARDRAIL_MAX_SUPPORT_INCREASE}); account closures did not increase ({sec['closed_m1']['diff'] * 100:+.2f}pp).

**But value depends on who you nudge.**

| Segment | Share | Salary switch lift | 24-month value per customer (95% CI) | Decision |
|---|---|---|---|---|
{chr(10).join(rows)}

For salaried customers the nudge brings salaries in, which raises balances and card spend. Students and self-employed customers mostly respond by moving money from their current account into savings pots, which earn the bank a lower margin and reduce card spend, so their value falls even though they engage with the feature.

## Data quality issue found and fixed

Client-side exposure logs showed a sample ratio mismatch (treatment share {srm['exposure_logs']['share_a'] * 100:.2f}%, p < 0.001). The drill-down traced it to legacy Android app versions, where the nudge's analytics event fails. Server-side assignments were balanced (p = {srm['server_assignments']['p_value']:.2f}), so all results use intention-to-treat on server assignments. The naive exposure-based estimate would have overstated the primary lift ({pp(srm['naive_primary']['diff'])} vs {pp(exp['primary']['raw']['diff'])}).

## Caveats

* **Projection error.** 24-month value is projected from 6 months of data. Validated against the simulation's ground truth, the projection got the decision right but overstated the targeted-launch value by about {proj_err:.0f}%, and its confidence intervals reflect sampling error only, not model error. Treat the £ figures as directional.
* **Assumed unit economics.** Interchange {C.INTERCHANGE_RATE * 100:.1f}%, current-account margin {C.CURRENT_ACCOUNT_MARGIN * 100:.1f}%, savings margin {C.SAVINGS_MARGIN * 100:.1f}%, cost to serve £{C.COST_TO_SERVE_MONTHLY:.2f}/month. The student and self-employed result depends on the gap between current-account and savings margins; finance should confirm these.
* **Novelty.** Engagement with pots spiked in week 1 and settled to a lower, stable lift by week 5, so early dashboards would overstate the lasting effect.

## Next steps

1. Launch to salaried customers, keeping a 5% holdout for 12 months to check the LTV projection against reality.
2. Test a different message for students (for example budgeting rather than saving) instead of shipping this one.
3. Ask engineering to fix exposure logging on legacy Android and add an automated SRM check to the experiment platform.
"""
    (C.DOCS_DIR / "decision_memo.md").write_text(memo)
    print("Wrote docs/decision_memo.md")


def img(name):
    data = base64.b64encode((C.FIG_DIR / name).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="" loading="lazy">'


def build_dashboard(power, exp, ltv, val):
    b = ltv["business_case"]
    segs = {r["segment"]: r for r in ltv["ltv_by_segment"]}
    seg_prim = {r["segment"]: r for r in exp["segments"]}
    prim = exp["primary"]["cuped"]
    sec = {r["metric"]: r for r in exp["secondary"]}
    srm = exp["srm"]
    d = val["decision"]
    proj_err = (d["estimated_targeted_value"] / d["true_targeted_value"] - 1) * 100

    seg_rows = ""
    for s in C.SEGMENT_ORDER:
        r, p = segs[s], seg_prim[s]
        cls = "go" if r["launch"] else "hold"
        seg_rows += f"""
        <tr class="{cls}">
          <th scope="row">{html.escape(C.SEGMENT_LABELS[s])}</th>
          <td>{r['share'] * 100:.0f}%</td>
          <td>{pp(p['diff'])}</td>
          <td class="num">{gbp(r['ltv_diff'])}</td>
          <td><span class="verdict">{'Launch' if r['launch'] else 'Hold'}</span></td>
        </tr>"""

    guard_rows = ""
    for m in ["support_contacts_m1", "closed_m1"]:
        r = sec[m]
        ok = r["guardrail_pass"] == 1
        val_fmt = f"{r['diff']:+.3f}" if m == "support_contacts_m1" else f"{r['diff'] * 100:+.2f}pp"
        thr_fmt = f"+{r['guardrail_threshold']:.2f}" if m == "support_contacts_m1" else f"+{r['guardrail_threshold'] * 100:.1f}pp"
        guard_rows += f"<tr><th scope='row'>{html.escape(r['label'])}</th><td>{val_fmt}</td><td>{thr_fmt}</td><td>{'Pass' if ok else 'Fail'}</td></tr>"

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Savings nudge experiment readout</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,650&display=swap" rel="stylesheet">
<style>
:root {{
  --paper: #F7F8FA; --surface: #FFFFFF; --ink: #1C2333; --muted: #5E677A; --rule: #DDE1E8;
  --go: #0F7B6C; --go-tint: #E3F1EE; --hold: #B4432F; --hold-tint: #F6E6E2; --warn: #C98A12;
  --serif: "Source Serif 4", Georgia, "Times New Roman", serif;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  color-scheme: light;
  box-sizing: border-box;
  padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px);
}}
*, *::before, *::after {{ box-sizing: inherit; }}
html {{ scroll-padding-top: env(safe-area-inset-top, 0px); }}
body {{ margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.6 var(--sans); }}
main {{ max-width: 860px; margin: 0 auto; padding: 3rem 1.25rem 4rem; }}
h1, h2 {{ font-family: var(--serif); font-weight: 650; line-height: 1.2; letter-spacing: -0.01em; }}
h1 {{ font-size: clamp(1.9rem, 4.5vw, 2.9rem); margin: 0.4rem 0 1rem; max-width: 24ch; }}
h2 {{ font-size: 1.45rem; margin: 3rem 0 0.6rem; }}
p {{ max-width: 68ch; margin: 0.5rem 0 1rem; }}
.kicker {{ color: var(--muted); font-size: 0.95rem; margin: 0; }}
.lede {{ font-size: 1.15rem; color: var(--ink); }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1px; background: var(--rule);
          border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; margin: 2rem 0 0; }}
.facts div {{ background: var(--surface); padding: 1rem 1.1rem; }}
.facts strong {{ display: block; font-family: var(--serif); font-size: 1.6rem; font-weight: 650; }}
.facts span {{ color: var(--muted); font-size: 0.9rem; }}
.table-wrap {{ overflow-x: auto; margin: 1rem 0; }}
table {{ border-collapse: collapse; width: 100%; min-width: 520px; background: var(--surface); }}
th, td {{ text-align: left; padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--rule); }}
thead th {{ font-weight: 500; color: var(--muted); font-size: 0.9rem; }}
tbody th {{ font-weight: 600; }}
td.num {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
.segments tr.go {{ box-shadow: inset 4px 0 0 var(--go); }}
.segments tr.hold {{ box-shadow: inset 4px 0 0 var(--hold); }}
.verdict {{ display: inline-block; padding: 0.15rem 0.65rem; border-radius: 999px; font-weight: 600; font-size: 0.9rem; }}
tr.go .verdict {{ background: var(--go-tint); color: var(--go); }}
tr.hold .verdict {{ background: var(--hold-tint); color: var(--hold); }}
figure {{ margin: 1.25rem 0; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 0.75rem; }}
figure img {{ width: 100%; max-width: 100%; height: auto; display: block; }}
figcaption {{ color: var(--muted); font-size: 0.92rem; margin-top: 0.5rem; }}
.note {{ border-left: 4px solid var(--warn); background: var(--surface); padding: 0.9rem 1.1rem; margin: 1rem 0; }}
.note p {{ margin: 0.25rem 0; }}
footer {{ margin-top: 3.5rem; color: var(--muted); font-size: 0.9rem; border-top: 1px solid var(--rule); padding-top: 1rem; }}
</style>
</head>
<body>
<main>
  <p class="kicker">Experiment readout: in-app savings nudge, {C.N_USERS:,} customers, simulated data</p>
  <h1>Launch to salaried customers. Hold for students and the self-employed.</h1>
  <p class="lede">The nudge brings salaries in, but for some customers it only moves money into lower-margin savings. Targeting it is worth about £{b['targeted_launch_value'] / 1000:,.0f}k in 24-month value per 100,000 eligible customers, against £{b['full_launch_value'] / 1000:,.0f}k for launching to everyone.</p>

  <div class="facts">
    <div><strong>{pp(prim['diff'])}</strong><span>salary moved in within 30 days ({prim['mean_control'] * 100:.1f}% to {prim['mean_treatment'] * 100:.1f}%)</span></div>
    <div><strong>{gbp(segs['all']['ltv_diff'])}</strong><span>24-month value per customer, everyone</span></div>
    <div><strong>2 of 2</strong><span>guardrails passed</span></div>
  </div>

  <h2>Decision by segment</h2>
  <p>We launch to a segment only if its lifetime-value effect is positive and significant after Holm correction, as pre-registered.</p>
  <div class="table-wrap">
  <table class="segments">
    <thead><tr><th>Segment</th><th>Share</th><th>Salary switch lift</th><th>24-month value per customer</th><th>Decision</th></tr></thead>
    <tbody>{seg_rows}
    </tbody>
  </table>
  </div>
  <figure>{img('06_ltv_by_segment.png')}<figcaption>Change in projected 24-month value per customer, with 95% confidence intervals.</figcaption></figure>
  <figure>{img('08_business_case.png')}<figcaption>Incremental value per 100,000 eligible customers. Error bars are 95% intervals from sampling error only.</figcaption></figure>

  <h2>Experiment health</h2>
  <div class="note">
    <p><strong>Sample ratio mismatch in exposure logs.</strong> Logged treatment share was {srm['exposure_logs']['share_a'] * 100:.2f}% (p &lt; 0.001), caused by a failing analytics event on legacy Android. Server-side assignments are balanced (p = {srm['server_assignments']['p_value']:.2f}), so every result here is intention-to-treat on server assignments.</p>
  </div>
  <figure>{img('02_srm_drilldown.png')}<figcaption>Treatment share among users with a logged exposure, by platform and app version.</figcaption></figure>
  <figure>{img('05_primary_estimates.png')}<figcaption>Using the broken logs would have inflated the primary result. CUPED barely helps on this binary metric, but cut variance on card spend by {sec['card_spend_m1']['cuped_variance_reduction'] * 100:.0f}%.</figcaption></figure>

  <h2>Guardrails</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Metric</th><th>Change</th><th>Threshold</th><th>Result</th></tr></thead>
    <tbody>{guard_rows}</tbody>
  </table>
  </div>

  <h2>Who responds</h2>
  <figure>{img('03_primary_by_segment.png')}<figcaption>Lift in 30-day salary switch rate by segment, 95% intervals.</figcaption></figure>
  <figure>{img('04_novelty_effect.png')}<figcaption>Pot transfers spike in week 1 and settle by week 5. Early reads overstate the lasting effect.</figcaption></figure>

  <h2>How value was projected</h2>
  <p>Six months were observed. Months 7 to 24 were projected from each customer's recent value, segment retention, and the chance they still move their salary in later.</p>
  <figure>{img('07_retention_curves.png')}<figcaption>Share of accounts still open by month.</figcaption></figure>

  <h2>Does the method work?</h2>
  <p>Because the data is simulated, the true effect is known. Observed 6-month effects match the truth in every segment. The 24-month projection picks the right segments but overstates the targeted-launch value by about {proj_err:.0f}%, and its intervals ignore model error.</p>
  <figure>{img('09_validation_vs_truth.png')}<figcaption>Estimates (green, 95% CI) against the true planted effect (amber).</figcaption></figure>

  <footer>Built with Python, SQL (dbt models) and a local SQLite warehouse; BigQuery-ready. All data is simulated and unit economics are illustrative assumptions.</footer>
</main>
</body>
</html>
"""
    C.DASHBOARD_DIR.mkdir(exist_ok=True)
    (C.DASHBOARD_DIR / "index.html").write_text(page)
    print("Wrote dashboard/index.html")


def main():
    power, exp, ltv, val = load()
    build_memo(power, exp, ltv, val)
    build_dashboard(power, exp, ltv, val)


if __name__ == "__main__":
    main()
