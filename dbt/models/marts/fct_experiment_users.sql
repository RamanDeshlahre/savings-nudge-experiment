-- One row per randomised customer: assignment, covariates and 30-day outcomes.
-- This is the main table for the experiment analysis.
with month_1 as (
    select * from {{ ref('stg_monthly_activity') }} where month_number = 1
),

month_6 as (
    select user_id from {{ ref('stg_monthly_activity') }} where month_number = 6
)

select
    a.user_id,
    a.variant,
    a.is_treatment,
    case when e.user_id is not null then 1 else 0 end as exposure_logged,

    -- covariates (all measured before or independent of treatment)
    c.segment,
    c.platform,
    c.app_version,
    c.acquisition_channel,
    c.tenure_days,
    c.age,
    p.pre_card_spend,
    p.pre_txn_count,
    p.pre_avg_balance,

    -- primary metric
    case when s.first_salary_day <= 30 then 1 else 0 end as salary_switched_30d,

    -- secondary metrics
    case when s.first_salary_day is not null then 1 else 0 end as salary_switched_6m,
    case when pe.user_id is not null then 1 else 0 end as pot_created_30d,
    m1.card_spend as card_spend_m1,
    m1.avg_savings_balance as savings_balance_m1,

    -- guardrails
    m1.support_contacts as support_contacts_m1,
    m1.closed_end_of_month as closed_m1,
    case when m6.user_id is not null then 1 else 0 end as active_m6

from {{ ref('stg_assignments') }} as a
left join {{ ref('stg_exposures') }} as e using (user_id)
left join {{ ref('stg_customers') }} as c using (user_id)
left join {{ ref('stg_pre_period_activity') }} as p using (user_id)
left join {{ ref('stg_salary_events') }} as s using (user_id)
left join {{ ref('stg_pot_events') }} as pe using (user_id)
left join month_1 as m1 using (user_id)
left join month_6 as m6 using (user_id)
