"""
Central configuration for the savings-nudge experiment project.

Everything that is an *assumption* lives here, so it is easy to see, question
and change. Unit economics are illustrative, loosely based on public UK
banking figures, and are NOT any real bank's internal numbers.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
TRUTH_DIR = ROOT / "data" / "ground_truth"
WAREHOUSE = ROOT / "data" / "warehouse.db"          # local stand-in for BigQuery
DBT_DIR = ROOT / "dbt"
FIG_DIR = ROOT / "outputs" / "figures"
TABLE_DIR = ROOT / "outputs" / "tables"
RESULTS_DIR = ROOT / "outputs" / "results"
DASHBOARD_DIR = ROOT / "dashboard"
DOCS_DIR = ROOT / "docs"

# ---------------------------------------------------------------------------
# Experiment design
# ---------------------------------------------------------------------------
SEED = 42
N_USERS = 1_000_000          # eligible customers randomised
TREATMENT_SHARE = 0.5        # 50/50 split, done server-side
OBSERVED_MONTHS = 6          # months of post-exposure data we "have"
LTV_HORIZON_MONTHS = 24      # horizon for lifetime value
ALPHA = 0.05
POWER = 0.80

# Guardrail thresholds (pre-registered, see docs/pre_registration.md)
GUARDRAIL_MAX_SUPPORT_INCREASE = 0.10   # extra support contacts per user in month 1
GUARDRAIL_MAX_CLOSURE_INCREASE = 0.003  # +0.3pp account closure in month 1

# ---------------------------------------------------------------------------
# Unit economics (illustrative assumptions, per customer)
# ---------------------------------------------------------------------------
INTERCHANGE_RATE = 0.002            # 0.2% of debit card spend (UK debit cap)
CURRENT_ACCOUNT_MARGIN = 0.030      # annual net interest margin on current-account balances
SAVINGS_MARGIN = 0.012              # annual margin on savings balances (bank pays interest)
COST_TO_SERVE_MONTHLY = 1.20        # £ per active customer per month
COST_PER_SUPPORT_CONTACT = 4.00     # £ per support conversation
ANNUAL_DISCOUNT_RATE = 0.10         # for discounting future value

# ---------------------------------------------------------------------------
# Simulation parameters (the "true world" we plant, then try to recover)
# ---------------------------------------------------------------------------
# share: population share
# salary_logit: baseline log-odds of moving salary in within 30 days
# salary_tau: TRUE treatment effect on salary log-odds  <-- planted heterogeneity
# pot_logit: baseline log-odds of opening a savings pot within 30 days
# save_a, save_b: Beta params for share of balance moved into savings
# spend_mu / bal_mu: log of typical monthly card spend / balance before salary moves
# churn: baseline monthly account-closure hazard
# late_switch: monthly hazard of moving salary in after day 30
SEGMENTS = {
    "student": dict(share=0.22, salary_logit=-3.3, salary_tau=0.05, pot_logit=-1.3,
                    save_a=4.0, save_b=4.0, spend_mu=5.40, bal_mu=5.30,
                    churn=0.025, late_switch=0.003, age=(18, 23)),
    "salaried_under_35": dict(share=0.38, salary_logit=-2.0, salary_tau=0.70, pot_logit=-1.2,
                              save_a=2.0, save_b=6.0, spend_mu=6.45, bal_mu=6.50,
                              churn=0.012, late_switch=0.010, age=(23, 34)),
    "salaried_35_plus": dict(share=0.25, salary_logit=-2.3, salary_tau=0.60, pot_logit=-1.5,
                             save_a=2.0, save_b=6.0, spend_mu=6.65, bal_mu=6.95,
                             churn=0.008, late_switch=0.008, age=(35, 64)),
    "self_employed": dict(share=0.15, salary_logit=-2.9, salary_tau=0.30, pot_logit=-1.6,
                          save_a=2.0, save_b=5.0, spend_mu=6.50, bal_mu=7.00,
                          churn=0.015, late_switch=0.005, age=(25, 64)),
}

SALARY_BALANCE_MULTIPLIER = 3.0   # balances when salary is paid in
SALARY_SPEND_MULTIPLIER = 2.0     # card spend when salary is paid in
POT_TREATMENT_LOGIT_LIFT = 1.1    # nudge strongly increases pot creation (all segments)
SAVINGS_SHARE_TREATMENT_LIFT = 0.15  # nudged savers move 15% more into pots
SPEND_REDUCTION_PER_SAVED_SHARE = 0.35
SUPPORT_BASE_RATE = 0.10          # contacts per user per month
SUPPORT_TREATMENT_EXTRA = 0.05    # extra contacts per month in months 1-2 (questions about pots)

# Novelty effect on weekly pot transfers (treatment only)
NOVELTY_AMPLITUDE = 1.6
NOVELTY_DECAY_WEEKS = 1.3
PERSISTENT_LIFT = 0.20
WEEKS_TRACKED = 8

# Planted logging bug: treatment exposure events fail on old Android app versions
OLD_APP_BASE_LOGIT = -2.0
EXPOSURE_LOG_FAILURE_RATE = 0.80

SEGMENT_ORDER = ["student", "salaried_under_35", "salaried_35_plus", "self_employed"]
SEGMENT_LABELS = {
    "student": "Students",
    "salaried_under_35": "Salaried, under 35",
    "salaried_35_plus": "Salaried, 35+",
    "self_employed": "Self-employed",
}


def monthly_discount(month: int) -> float:
    """Discount factor for month m (1-indexed), using the annual rate."""
    return 1.0 / (1.0 + ANNUAL_DISCOUNT_RATE) ** (month / 12.0)
