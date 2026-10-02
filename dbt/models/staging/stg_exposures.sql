-- Client-side exposure logs, deduplicated to one row per user.
select
    user_id,
    min(variant) as exposed_variant,
    min(days_since_assignment) as first_exposure_day
from {{ source('raw', 'exposures') }}
group by user_id
