# Pre-registration: savings nudge experiment

*Written before launch. Its purpose is to fix the hypotheses, metrics and decision rules in advance, so the results can't be reinterpreted after we see them.*

## Background

Customers who pay their salary into the account become far more valuable: higher balances, more card spend and lower churn. Many customers open an account but keep their salary elsewhere. The product squad has built an in-app nudge that suggests opening a savings pot and moving their salary in.

## Hypotheses

**H1 (primary).** The nudge increases the share of customers who move their salary in within 30 days.

**H2 (value).** The nudge increases 24-month customer value. We expect this to vary by segment, because some customers may respond by moving existing money into savings rather than bringing new money in.

## Population and randomisation

Eligible customers have 1 to 12 months of tenure and no salary deposit yet. They are randomised 50/50 at customer level by the experiment service (server-side). Analysis is intention-to-treat on server-side assignment. Client exposure logs are used only for health checks.

## Metrics

**Primary.** Salary moved in within 30 days of assignment (0/1).

**Secondary.**
- Savings pot opened within 30 days
- Salary moved in within 6 months
- Card spend in month 1
- Savings balance in month 1
- Account still open at month 6
- Weekly pot transfers, weeks 1 to 8, used to check for a novelty effect

**Value.** Discounted 6-month value (observed) and 24-month value (projected).

| Guardrail | Threshold |
|---|---|
| Support contacts per customer, month 1 | Upper 95% bound must be below +0.10 |
| Account closures, month 1 | Upper 95% bound must be below +0.3pp |

## Analysis plan

1. **Sample ratio mismatch check.** Run a chi-square test on server assignments and on exposure logs. If server assignments fail (p < 0.001), stop and investigate. If only the logs fail, diagnose the cause and analyse on server assignments.
2. **Primary metric.** Difference in proportions with a Welch standard error and a two-sided α = 0.05. CUPED uses pre-period card spend and transaction count as the covariate. We report both the raw and the CUPED estimate.
3. **Segments.** Students, salaried under 35, salaried 35+ and self-employed are defined from profile data before the experiment. P-values are Holm-corrected across the four segments.
4. **Value.** Project 24-month value from 6 months of data: observed value, plus a tail based on each customer's recent value, segment-and-arm retention, and late salary switching.

## Sample size

The primary metric needs about 15k customers per arm. That is enough to detect a +1pp lift on a 10% baseline with 80% power.

The value question is harder. It needs about 70k customers per arm *within the smallest segment* (self-employed, about 15%) to detect £1.50 of 24-month value with a standard deviation of about £100. That works out to about 930k customers in total, so we randomise 1,000,000.

## Decision rule

Launch to a segment if all of the following hold:
- its 24-month value effect is positive and significant after Holm correction, and
- the guardrails pass overall.

Hold a segment whose value effect is negative or not significant, and consider a follow-up test for it.

## Duration

Assignment happens at launch. Outcomes are read after 6 months, and we do not peek at results for decisions before then.

Weekly monitoring covers only experiment health (sample ratio mismatch) and guardrails.
