-- Server-side allocation: the source of truth for intention-to-treat analysis.
select
    user_id,
    variant,
    case when variant = 'treatment' then 1 else 0 end as is_treatment,
    assigned_date
from {{ source('raw', 'assignments') }}
