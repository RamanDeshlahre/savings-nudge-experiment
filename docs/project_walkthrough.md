# Project walkthrough and interview prep

This is your study guide. Go through it step by step with the code open beside it. By the end you should be able to explain every number, chart and decision without notes.

## The story in 30 seconds

> "I simulated a bank experiment on a million customers testing a savings nudge. The primary metric went up 5.7 points, which looks like an easy win. But when I modelled lifetime value by segment, the nudge only created value for salaried customers. Students and self-employed customers just moved money into lower-margin savings. So I recommended a targeted launch, worth about 20% more than launching to everyone. Along the way I caught a sample ratio mismatch caused by a logging bug. Because I simulated the data, I could check my methods against the true effects. That showed my value projection got the decision right but overstated the pounds by about 11%."

Practise saying this out loud until it feels natural.

## Step 1: Simulate the data (`src/01_simulate_data.py`)

**What it does.** It creates 1M customers with segments, platforms and pre-period behaviour, plus 6 months of monthly activity. The key idea is **potential outcomes**. For every customer we simulate what happens *both* in control and in treatment, using the same random numbers. We then only "show" the analysis the arm they were assigned to.

**Why it matters.** Saving both outcomes in `data/ground_truth/` means we know the *true* effect, which no real experiment gives you. Step 6 uses it to grade the methods.

**What's planted.**
- Segment-dependent effects (`salary_tau` in `config.py`)
- A novelty effect
- A logging bug on legacy Android
- Pre-period behaviour that predicts outcomes

**Be ready to explain** why the data is simulated: no public dataset links a bank experiment to revenue, and simulation lets you validate the method. Be upfront that it's simulated. That's a strength, not something to hide.

## Step 2: Build the warehouse (`src/02_build_warehouse.py`, `dbt/`)

**What it does.** It loads raw CSVs and builds the dbt models: views for staging, tables for marts. Then it runs the data tests.

**Models.**
- `stg_*`: light cleaning, plus the segment derived from age and occupation.
- `fct_experiment_users`: one row per customer, holding assignment, covariates and 30-day outcomes.
- `fct_user_monthly_value`: value per customer per month. The unit economics come from dbt `vars`, so finance can change assumptions in one place.
- `agg_weekly_pot_transfers`: weekly totals *and sums of squares*, so standard errors can be computed without storing every zero.

**Tests.** Unique and not-null user IDs, accepted values, "one row per user-month", and "no activity after account closure".

**Be ready to explain** why the left joins start from `stg_assignments`. Every randomised customer must appear in the table, even those with no events. Dropping customers who did nothing biases the result.

## Step 3: Power analysis (`src/03_power_analysis.py`)

**Formula** for two proportions:

n per arm = (z₁₋α/₂ + z₁₋β)² × [p₁(1−p₁) + p₂(1−p₂)] / δ²

With p₁ = 10%, δ = 1pp, α = 0.05 and power = 80%, that gives about 14.7k per arm.

**Formula** for means:

n per arm = 2(z₁₋α/₂ + z₁₋β)² σ² / δ²

With σ = £100 and δ = £1.50, that gives about 70k per arm. Since that's needed *within* a segment that is 15% of customers, the total is about 930k.

**Key insight.** Size the experiment for the hardest question you must answer, not the primary metric.

## Step 4: Experiment analysis (`src/04_experiment_analysis.py`)

**4a. Sample ratio mismatch (SRM).** A chi-square test of observed counts against a 50/50 split.
- Exposure logs show a 48.57% treatment share, p ≈ 10⁻¹⁷⁵.
- The drill-down shows legacy Android at 16.6% treatment. The analytics event fails there.
- Server-side assignments are balanced (p = 0.85).

**Lesson.** Always check SRM first. Analyse on the assignment source of truth (intention-to-treat). The dropped users were less engaged, so the naive estimate is inflated: 5.97pp against the true 5.69pp.

**4b. Primary metric.** A Welch difference in proportions: 9.6% to 15.2%, +5.7pp.

**CUPED.** Adjust each customer's outcome with a pre-experiment covariate:

y_adj = y − θ(x − x̄), where θ = cov(y, x) / var(x)

The covariate is measured before treatment, so it's independent of assignment. The estimate stays unbiased and the variance falls by about corr(x, y)².
- On the binary salary metric it only cut variance by about 4%, because the correlation is weak.
- On card spend it cut variance by about 61%, because past spend strongly predicts future spend.

Be honest that CUPED helps most on continuous metrics with a strong pre-period analogue.

**4c. Guardrails.** Support contacts rose by 0.051 per customer, under the 0.10 threshold. Closures didn't rise. Note that each guardrail is judged on the *upper CI bound*, not the point estimate.

**4d. Segments.** The lift was +9.6pp for salaried under 35, +6.9pp for salaried 35+, +1.7pp for self-employed and +0.2pp for students. Holm correction controls the chance of *any* false positive across the four tests. It's less conservative than Bonferroni.

**4e. Novelty effect.** The relative lift in pot transfers was about +480% in week 1 and settled near +150% by weeks 5 to 8. If you decided after one week, you'd overstate the lasting effect.

## Step 5: Lifetime value (`src/05_ltv_model.py`)

**LTV = observed discounted value (months 1–6) + projected tail (months 7–24).**

**Retention, r.** Monthly retention per segment and arm, estimated from months 4 to 6, after early churn settles.

**Late switching.** Some control customers would have moved their salary in later anyway. Ignoring that overstates the effect, because control has more customers left who could switch. So the model adds dv × P(switch by month k), where:
- h is the monthly late-switch rate, measured in months 2 to 6.
- dv is the value uplift from switching, estimated *within customer* (the same control customer before and after switching). This avoids selection bias, since switchers are more engaged to begin with.

**Results.**

| Segment | Change in 24-month value per customer |
|---|---|
| Salaried under 35 | +£6.85 |
| Salaried 35+ | +£7.49 |
| Students | −£1.76 |
| Self-employed | −£2.37 |

**Why students lose value.** They open pots and move money from the current account (3% margin) into savings (1.2% margin). They also spend a little less on card. That costs margin without bringing new money in.

**Business case per 100k eligible customers.** A targeted launch is worth £448k, against £373k for launching to everyone.

## Step 6: Validation (`src/06_validate_against_truth.py`)

- **The ITT estimate covers the truth; the naive estimate doesn't.** This proves the SRM fix mattered.
- **6-month value covers the truth in all segments.** The data and the design are sound.
- **24-month LTV gets the direction and the decision right but misses on magnitude.** The CIs miss in 3 of 4 segments, and the targeted value is overstated by about 11%. The reasons:
  - The confidence intervals only capture *sampling* error, not *model* error.
  - Extrapolation amplifies small 6-month errors.

**This is your best interview moment.** It shows you know the limits of your own model. The fix you'd propose is a long-running holdout group to measure real 12-month value, and to recalibrate the model against it.

## Step 7: Reports (`src/07_build_reports.py`)

- The decision memo in `docs/decision_memo.md` puts the recommendation first, with evidence, caveats and next steps.
- The HTML dashboard is a readout a product squad can open in any browser.

## Likely interview questions

**"Your primary metric was hugely significant. Why not just ship?"**
Statistical significance on a proxy metric isn't value. The salary switch rate rose in every segment, but lifetime value fell for students and the self-employed. I'd ship only where value goes up.

**"What is SRM and what do you do when you see it?"**
SRM is when the observed split differs from the designed split. It means something non-random is removing or adding users, so the results may be biased. Stop, find the cause, and drill down by platform, version, date and browser. Here, server assignments were fine and only the logs were broken. So I analysed intention-to-treat and asked engineering to fix the logging. If the *assignment* itself is broken, the experiment usually needs a re-run.

**"Why intention-to-treat?"**
Randomisation only guarantees comparable groups for everyone *assigned*. Filtering on anything that happens after assignment, such as exposure, opening the app or clicking, can break that balance.

**"Explain CUPED to a product manager."**
"We use what each customer did *before* the test to remove noise that has nothing to do with the feature. It's like comparing each runner's race time against their personal best rather than against the whole field. The same test gives sharper answers, or the same answers sooner."

**"You tested four segments. Isn't that p-hacking?"**
The segments were pre-registered, and I applied Holm correction. The effects are also huge relative to their standard errors, and they have a clear mechanism.

**"How would you run this at a real bank?"**
- Segment definitions must use only data from before randomisation.
- Agree the unit economics with finance before launch.
- Keep a long-term holdout to validate the LTV model.
- Automate SRM checks.
- Check for interference: for example, joint-account partners in different arms.
- Use sequential testing if the team wants to monitor results early.

**"What would you do differently?"**
- Model uncertainty in the projection, for example by bootstrapping the whole pipeline or using a Bayesian model, so the intervals are honest.
- Consider an uplift model to target individuals rather than whole segments.
- Run sensitivity analysis on the margin assumptions.

**"What's the weakest part of this project?"**
The 24-month projection. It's directionally right but overconfident. I'd say so in the memo, and I did.

## Things to try yourself (to make it truly yours)

1. Change the savings margin to 0.02, both as `SAVINGS_MARGIN` in `config.py` and as `savings_margin` in `dbt/dbt_project.yml` (the pipeline checks they match), then re-run. Does the student decision flip? This is sensitivity analysis.
2. Set `EXPOSURE_LOG_FAILURE_RATE = 0`. The SRM disappears and the naive and ITT estimates agree.
3. Add a sequential testing or bootstrap section.
4. Run the dbt models on BigQuery, following `docs/bigquery_setup.md`, and screenshot the lineage graph for the README.
