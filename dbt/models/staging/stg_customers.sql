-- One row per customer, with the analysis segment derived from profile data.
select
    user_id,
    age,
    occupation,
    platform,
    app_version,
    acquisition_channel,
    tenure_days,
    case
        when occupation = 'student' then 'student'
        when occupation = 'self_employed' then 'self_employed'
        when age < 35 then 'salaried_under_35'
        else 'salaried_35_plus'
    end as segment
from {{ source('raw', 'customers') }}
