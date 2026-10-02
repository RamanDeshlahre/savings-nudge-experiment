-- Fails if an account has activity after the month it was closed.
with closures as (
    select user_id, min(month_number) as closed_month
    from {{ ref('fct_user_monthly_value') }}
    where closed_end_of_month = 1
    group by user_id
)

select v.user_id, v.month_number
from {{ ref('fct_user_monthly_value') }} as v
inner join closures as c using (user_id)
where v.month_number > c.closed_month
