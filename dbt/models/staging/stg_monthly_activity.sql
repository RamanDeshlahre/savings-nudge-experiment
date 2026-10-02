select
    user_id,
    month_number,
    card_spend,
    avg_current_balance,
    avg_savings_balance,
    support_contacts,
    has_salary_deposit,
    closed_end_of_month
from {{ source('raw', 'monthly_activity') }}
