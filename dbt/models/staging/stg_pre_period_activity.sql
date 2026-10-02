select
    user_id,
    card_spend_30d as pre_card_spend,
    txn_count_30d as pre_txn_count,
    avg_balance_30d as pre_avg_balance
from {{ source('raw', 'pre_period_activity') }}
