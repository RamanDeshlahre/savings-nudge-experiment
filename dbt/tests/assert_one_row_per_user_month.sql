-- Fails if any customer has more than one row for the same month.
select user_id, month_number, count(*) as n_rows
from {{ ref('fct_user_monthly_value') }}
group by user_id, month_number
having count(*) > 1
