# Savings nudge: launch recommendation

*Decision memo for the product squad and finance partner. Simulated data; see README.*

## Recommendation

**Launch the savings nudge to salaried customers only (63% of eligible customers). Hold it for students and self-employed customers.**

A targeted launch is worth an estimated **£448k in 24-month value per 100,000 eligible customers** (95% CI £416k to £479k), about 20% more than launching to everyone (£373k), because for two segments the nudge destroys value.

## What we tested

Eligible customers (1 to 12 months tenure, salary not yet paid in) were randomised 50/50 server-side. Treatment saw an in-app nudge to open a savings pot and move their salary in. 1,000,000 customers took part; the pre-registered sample size was driven by the need to detect a £1.50 lifetime-value difference within the smallest segment (≈0.93M customers), not by the primary metric (≈29k).

## Results

**Primary metric.** The share of customers moving their salary in within 30 days rose from 9.6% to 15.2% (+5.7pp, 95% CI 5.56 to 5.81pp, a 59% relative lift).

**Guardrails passed.** Support contacts in month 1 rose by 0.051 per customer (threshold 0.1); account closures did not increase (-0.08pp).

**But value depends on who you nudge.**

| Segment | Share | Salary switch lift | 24-month value per customer (95% CI) | Decision |
|---|---|---|---|---|
| Students | 22% | +0.2pp | −£1.76 (−£1.92 to −£1.60) | Hold |
| Salaried, under 35 | 38% | +9.6pp | +£6.85 (+£6.30 to +£7.40) | **Launch** |
| Salaried, 35+ | 25% | +6.9pp | +£7.49 (+£6.54 to +£8.44) | **Launch** |
| Self-employed | 15% | +1.7pp | −£2.37 (−£3.35 to −£1.39) | Hold |

For salaried customers the nudge brings salaries in, which raises balances and card spend. Students and self-employed customers mostly respond by moving money from their current account into savings pots, which earn the bank a lower margin and reduce card spend, so their value falls even though they engage with the feature.

## Data quality issue found and fixed

Client-side exposure logs showed a sample ratio mismatch (treatment share 48.57%, p < 0.001). The drill-down traced it to legacy Android app versions, where the nudge's analytics event fails. Server-side assignments were balanced (p = 0.85), so all results use intention-to-treat on server assignments. The naive exposure-based estimate would have overstated the primary lift (+6.0pp vs +5.7pp).

## Caveats

* **Projection error.** 24-month value is projected from 6 months of data. Validated against the simulation's ground truth, the projection got the decision right but overstated the targeted-launch value by about 11%, and its confidence intervals reflect sampling error only, not model error. Treat the £ figures as directional.
* **Assumed unit economics.** Interchange 0.2%, current-account margin 3.0%, savings margin 1.2%, cost to serve £1.20/month. The student and self-employed result depends on the gap between current-account and savings margins; finance should confirm these.
* **Novelty.** Engagement with pots spiked in week 1 and settled to a lower, stable lift by week 5, so early dashboards would overstate the lasting effect.

## Next steps

1. Launch to salaried customers, keeping a 5% holdout for 12 months to check the LTV projection against reality.
2. Test a different message for students (for example budgeting rather than saving) instead of shipping this one.
3. Ask engineering to fix exposure logging on legacy Android and add an automated SRM check to the experiment platform.
