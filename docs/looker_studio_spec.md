# Looker Studio dashboard spec

The repository ships a self-contained HTML readout in `dashboard/index.html`. If you've run the BigQuery setup, you can also build a live dashboard in Looker Studio. It's free and is a different product from Looker (which many product teams use), but building one shows the same skill.

## Data sources

All three tables come from the `analytics` dataset:

1. `fct_experiment_users`
2. `fct_user_monthly_value`
3. `agg_weekly_pot_transfers`

## Calculated fields

Add these on `fct_experiment_users`:

- **Salary switch rate**: `AVG(salary_switched_30d)`
- **Pot open rate**: `AVG(pot_created_30d)`
- **Support contacts per user**: `AVG(support_contacts_m1)`
- **Exposure logged share**: `AVG(exposure_logged)`

Add this on `fct_user_monthly_value`:

- **Value per assigned user**: `SUM(net_value) / COUNT_DISTINCT(user_id)`. This divides by active users, so filter to month 1 for a like-for-like comparison.

## Page 1: experiment health

- A scorecard pair showing users per variant from `fct_experiment_users`.
- A table of platform × app_version × variant with *Exposure logged share*. This shows the legacy Android problem at a glance.

## Page 2: primary and guardrails

- A bar chart of *Salary switch rate* by variant.
- A bar chart of *Salary switch rate* by segment, broken down by variant.
- Scorecards for *Support contacts per user* and month-1 closure rate, each by variant.

## Page 3: value

- A time series of `SUM(net_value)` by `month_number`, broken down by variant, with a segment filter control.
- A line chart of `transfers_per_user` by `week_number` and variant from `agg_weekly_pot_transfers`. This shows the novelty effect.

## Note on uncertainty

Looker Studio doesn't compute confidence intervals. Keep it for monitoring, and use the Python analysis for the statistical read-out.
