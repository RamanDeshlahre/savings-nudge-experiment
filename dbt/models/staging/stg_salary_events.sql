select
    user_id,
    first_salary_day
from {{ source('raw', 'salary_events') }}
