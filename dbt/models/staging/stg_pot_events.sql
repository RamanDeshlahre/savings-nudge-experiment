select
    user_id,
    pot_created_day
from {{ source('raw', 'pot_events') }}
