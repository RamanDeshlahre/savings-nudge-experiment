select
    user_id,
    week_number,
    transfers
from {{ source('raw', 'weekly_pot_transfers') }}
