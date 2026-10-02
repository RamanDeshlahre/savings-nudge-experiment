-- One row per open account per month, with the value it generated for the bank.
-- Unit economics come from dbt vars so finance can change assumptions in one place.
select
    m.user_id,
    a.variant,
    a.is_treatment,
    c.segment,
    m.month_number,
    m.has_salary_deposit,
    m.closed_end_of_month,
    m.card_spend * {{ var('interchange_rate') }} as interchange_revenue,
    m.avg_current_balance * {{ var('current_account_margin') }} / 12.0 as current_account_margin,
    m.avg_savings_balance * {{ var('savings_margin') }} / 12.0 as savings_margin,
    {{ var('cost_to_serve_monthly') }} as cost_to_serve,
    m.support_contacts * {{ var('cost_per_support_contact') }} as support_cost,
    m.card_spend * {{ var('interchange_rate') }}
        + m.avg_current_balance * {{ var('current_account_margin') }} / 12.0
        + m.avg_savings_balance * {{ var('savings_margin') }} / 12.0
        - {{ var('cost_to_serve_monthly') }}
        - m.support_contacts * {{ var('cost_per_support_contact') }} as net_value
from {{ ref('stg_monthly_activity') }} as m
inner join {{ ref('stg_assignments') }} as a using (user_id)
inner join {{ ref('stg_customers') }} as c using (user_id)
