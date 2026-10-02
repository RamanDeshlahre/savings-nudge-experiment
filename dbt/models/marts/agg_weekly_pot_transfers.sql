-- Weekly pot transfers per ASSIGNED user (intention-to-treat), by arm.
-- Sum of squares is kept so we can compute standard errors without
-- materialising every zero-transfer user-week.
with arm_sizes as (
    select variant, count(*) as n_assigned
    from {{ ref('stg_assignments') }}
    group by variant
)

select
    w.week_number,
    a.variant,
    n.n_assigned,
    sum(w.transfers) as total_transfers,
    sum(w.transfers * w.transfers) as sum_sq_transfers,
    sum(w.transfers) * 1.0 / n.n_assigned as transfers_per_user
from {{ ref('stg_weekly_pot_transfers') }} as w
inner join {{ ref('stg_assignments') }} as a using (user_id)
inner join arm_sizes as n using (variant)
group by w.week_number, a.variant, n.n_assigned
