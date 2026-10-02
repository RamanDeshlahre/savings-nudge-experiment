"""
STEP 1 - Simulate the raw data.

We simulate a UK digital bank running an experiment on 1,000,000 eligible
customers: people with 1-12 months of tenure who have NOT yet moved their
salary into the account. Treatment customers see an in-app "savings nudge"
encouraging them to open a savings pot and pay their salary in.

Why simulate? No public dataset links a real bank experiment to revenue.
Simulating lets us plant the TRUE effects and then check that our analysis
recovers them (method validation).

For every customer we simulate BOTH potential outcomes (what would happen in
control AND in treatment) using shared random numbers. Only the outcome for the
arm they were actually assigned to goes into the "raw" tables; both go into
data/ground_truth/, which the analysis never touches until the validation step.

Planted "real-world" problems:
  1. Heterogeneous effects: the nudge moves salaries for salaried customers,
     barely at all for students (who just shuffle money into savings).
  2. A novelty effect: pot transfers spike in week 1, then fade.
  3. A logging bug: treatment exposure events fail on old Android app
     versions -> sample ratio mismatch (SRM) if you analyse exposure logs.
  4. Pre-period behaviour that predicts outcomes -> CUPED can cut variance.

Outputs (CSV) in data/raw/ and data/ground_truth/.
"""
import time

import numpy as np
import pandas as pd

import config as C


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def main():
    t0 = time.time()
    rng = np.random.default_rng(C.SEED)
    n = C.N_USERS
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    C.TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    user_id = np.arange(1, n + 1)

    # ------------------------------------------------------------------
    # Customer attributes
    # ------------------------------------------------------------------
    seg_names = C.SEGMENT_ORDER
    seg_shares = np.array([C.SEGMENTS[s]["share"] for s in seg_names])
    seg_idx = rng.choice(len(seg_names), size=n, p=seg_shares / seg_shares.sum())
    segment = np.array(seg_names)[seg_idx]

    def per_seg(key):
        return np.array([C.SEGMENTS[s][key] for s in seg_names])[seg_idx]

    age_lo = np.array([C.SEGMENTS[s]["age"][0] for s in seg_names])[seg_idx]
    age_hi = np.array([C.SEGMENTS[s]["age"][1] for s in seg_names])[seg_idx]
    age = rng.integers(age_lo, age_hi + 1)
    occupation = np.where(segment == "student", "student",
                          np.where(segment == "self_employed", "self_employed", "employed"))

    platform = np.where(rng.random(n) < 0.45, "android", "ios")
    channel = rng.choice(["referral", "organic", "paid_social"], size=n, p=[0.55, 0.25, 0.20])
    channel_offset = np.select([channel == "referral", channel == "paid_social"], [0.10, -0.20], 0.0)
    tenure_days = rng.integers(30, 366, size=n)

    # latent engagement drives almost everything (and is what CUPED exploits)
    engagement = rng.normal(0, 1, n) + channel_offset

    # old app versions are more common among less engaged users
    old_app = rng.random(n) < sigmoid(C.OLD_APP_BASE_LOGIT - 1.0 * engagement)
    app_version = np.where(old_app, "5.x_legacy", "6.x_current")

    # ------------------------------------------------------------------
    # Pre-period behaviour (30 days before the experiment)
    # ------------------------------------------------------------------
    base_spend = np.exp(per_seg("spend_mu") + 0.45 * engagement + rng.normal(0, 0.35, n))
    base_balance = np.exp(per_seg("bal_mu") + 0.40 * engagement + rng.normal(0, 0.50, n))
    pre_spend = base_spend * np.exp(rng.normal(0, 0.25, n))
    pre_txn = rng.poisson(base_spend / 25.0)
    pre_balance = base_balance * np.exp(rng.normal(0, 0.20, n))

    # ------------------------------------------------------------------
    # Random assignment (server-side, 50/50)
    # ------------------------------------------------------------------
    treat = (rng.random(n) < C.TREATMENT_SHARE).astype(int)

    # ------------------------------------------------------------------
    # Potential outcomes in the first 30 days (shared uniforms = coupling)
    # ------------------------------------------------------------------
    u_salary = rng.random(n)
    salary_day = rng.integers(1, 31, size=n)
    lin_salary = per_seg("salary_logit") + 0.60 * engagement
    salary30 = {a: u_salary < sigmoid(lin_salary + a * per_seg("salary_tau")) for a in (0, 1)}

    u_pot = rng.random(n)
    pot_day = rng.integers(1, 31, size=n)
    lin_pot = per_seg("pot_logit") + 0.30 * engagement
    pot30 = {a: u_pot < sigmoid(lin_pot + a * C.POT_TREATMENT_LOGIT_LIFT) for a in (0, 1)}

    save_share_base = rng.beta(per_seg("save_a"), per_seg("save_b"))
    save_share = {a: np.minimum(0.9, save_share_base * (1 + a * C.SAVINGS_SHARE_TREATMENT_LIFT))
                  for a in (0, 1)}

    # ------------------------------------------------------------------
    # Monthly simulation for 24 months, both arms
    # ------------------------------------------------------------------
    churn_base = per_seg("churn")
    late_hazard = per_seg("late_switch")
    alive = {a: np.ones(n, bool) for a in (0, 1)}
    salary_now = {a: salary30[a].copy() for a in (0, 1)}
    first_salary_day = {a: np.where(salary30[a], salary_day, -1) for a in (0, 1)}
    ltv = {a: np.zeros(n) for a in (0, 1)}
    value6 = {a: np.zeros(n) for a in (0, 1)}

    monthly_path = C.RAW_DIR / "monthly_activity.csv"
    if monthly_path.exists():
        monthly_path.unlink()

    for m in range(1, C.LTV_HORIZON_MONTHS + 1):
        # shared randomness for this month
        bal_noise = np.exp(rng.normal(0, 0.15, n))
        spend_noise = np.exp(rng.normal(0, 0.20, n))
        u_churn = rng.random(n)
        u_late = rng.random(n)
        late_day = (m - 1) * 30 + rng.integers(1, 31, size=n)
        contacts_base = rng.poisson(C.SUPPORT_BASE_RATE, n)
        contacts_extra = rng.poisson(C.SUPPORT_TREATMENT_EXTRA, n) if m <= 2 else np.zeros(n, int)
        disc = C.monthly_discount(m)

        month_obs = {}
        for a in (0, 1):
            # late salary switches (after day 30)
            if m >= 2:
                new_switch = alive[a] & ~salary_now[a] & (u_late < late_hazard)
                salary_now[a] = salary_now[a] | new_switch
                first_salary_day[a] = np.where(new_switch, late_day, first_salary_day[a])

            sal = salary_now[a]
            pot = pot30[a]
            total_bal = base_balance * np.where(sal, C.SALARY_BALANCE_MULTIPLIER, 1.0) * bal_noise
            savings = np.where(pot, total_bal * save_share[a], 0.0)
            current = total_bal - savings
            spend = (base_spend * np.where(sal, C.SALARY_SPEND_MULTIPLIER, 1.0)
                     * np.where(pot, 1 - C.SPEND_REDUCTION_PER_SAVED_SHARE * save_share[a], 1.0)
                     * spend_noise)
            contacts = contacts_base + a * contacts_extra

            value = (spend * C.INTERCHANGE_RATE
                     + current * C.CURRENT_ACCOUNT_MARGIN / 12
                     + savings * C.SAVINGS_MARGIN / 12
                     - C.COST_TO_SERVE_MONTHLY
                     - contacts * C.COST_PER_SUPPORT_CONTACT)
            value = np.where(alive[a], value, 0.0)
            ltv[a] += disc * value
            if m <= C.OBSERVED_MONTHS:
                value6[a] += disc * value

            # account closure at end of month
            hazard = churn_base * np.where(sal, 0.6, 1.0) * np.where(pot, 0.9, 1.0)
            closes = alive[a] & (u_churn < hazard)
            month_obs[a] = dict(active=alive[a].copy(), spend=spend, current=current,
                                savings=savings, contacts=contacts, salary=sal.copy(),
                                closes=closes)
            alive[a] = alive[a] & ~closes

        # write the OBSERVED arm only, for active customers, first 6 months
        if m <= C.OBSERVED_MONTHS:
            pick = lambda key: np.where(treat == 1, month_obs[1][key], month_obs[0][key])
            active = pick("active")
            df = pd.DataFrame({
                "user_id": user_id,
                "month_number": m,
                "card_spend": np.round(pick("spend"), 2),
                "avg_current_balance": np.round(pick("current"), 2),
                "avg_savings_balance": np.round(pick("savings"), 2),
                "support_contacts": pick("contacts").astype(int),
                "has_salary_deposit": pick("salary").astype(int),
                "closed_end_of_month": pick("closes").astype(int),
            })[active]
            df.to_csv(monthly_path, mode="a", header=(m == 1), index=False)
        print(f"  month {m:2d} simulated ({time.time() - t0:.0f}s)")

    # ------------------------------------------------------------------
    # Observed (raw) tables
    # ------------------------------------------------------------------
    variant = np.where(treat == 1, "treatment", "control")

    pd.DataFrame({
        "user_id": user_id, "age": age, "occupation": occupation, "platform": platform,
        "app_version": app_version, "acquisition_channel": channel, "tenure_days": tenure_days,
    }).to_csv(C.RAW_DIR / "customers.csv", index=False)

    pd.DataFrame({
        "user_id": user_id, "variant": variant, "assigned_date": "2026-03-02",
    }).to_csv(C.RAW_DIR / "assignments.csv", index=False)

    # client-side exposure logs: the planted bug drops treatment events on old Android
    log_fails = (treat == 1) & (platform == "android") & old_app & (rng.random(n) < C.EXPOSURE_LOG_FAILURE_RATE)
    exp_df = pd.DataFrame({"user_id": user_id, "variant": variant, "platform": platform,
                           "app_version": app_version, "days_since_assignment": 0})
    exp_df[~log_fails].to_csv(C.RAW_DIR / "exposures.csv", index=False)

    pd.DataFrame({
        "user_id": user_id, "card_spend_30d": np.round(pre_spend, 2),
        "txn_count_30d": pre_txn, "avg_balance_30d": np.round(pre_balance, 2),
    }).to_csv(C.RAW_DIR / "pre_period_activity.csv", index=False)

    obs_first_salary = np.where(treat == 1, first_salary_day[1], first_salary_day[0])
    # only salary events inside the observed window are visible to us
    has_sal = (obs_first_salary > 0) & (obs_first_salary <= C.OBSERVED_MONTHS * 30)
    pd.DataFrame({"user_id": user_id[has_sal], "first_salary_day": obs_first_salary[has_sal]}) \
        .to_csv(C.RAW_DIR / "salary_events.csv", index=False)

    obs_pot = np.where(treat == 1, pot30[1], pot30[0])
    pd.DataFrame({"user_id": user_id[obs_pot], "pot_created_day": pot_day[obs_pot]}) \
        .to_csv(C.RAW_DIR / "pot_events.csv", index=False)

    # weekly pot transfers (novelty effect planted in treatment)
    weekly_path = C.RAW_DIR / "weekly_pot_transfers.csv"
    if weekly_path.exists():
        weekly_path.unlink()
    holders = np.where(obs_pot)[0]
    start_week = pot_day[holders] // 7 + 1
    is_t = treat[holders]
    base_rate = 0.8 * np.exp(0.2 * engagement[holders])
    for w in range(1, C.WEEKS_TRACKED + 1):
        lift = is_t * (C.NOVELTY_AMPLITUDE * np.exp(-(w - 1) / C.NOVELTY_DECAY_WEEKS) + C.PERSISTENT_LIFT)
        transfers = rng.poisson(base_rate * (1 + lift))
        keep = (w >= start_week) & (transfers > 0)
        pd.DataFrame({"user_id": user_id[holders][keep], "week_number": w,
                      "transfers": transfers[keep]}) \
            .to_csv(weekly_path, mode="a", header=(w == 1), index=False)

    # ------------------------------------------------------------------
    # Ground truth (never used by the analysis, only by the validation step)
    # ------------------------------------------------------------------
    pd.DataFrame({
        "user_id": user_id, "segment": segment,
        "salary30_control": salary30[0].astype(int), "salary30_treatment": salary30[1].astype(int),
        "pot30_control": pot30[0].astype(int), "pot30_treatment": pot30[1].astype(int),
        "value6_control": value6[0].round(4), "value6_treatment": value6[1].round(4),
        "ltv24_control": ltv[0].round(4), "ltv24_treatment": ltv[1].round(4),
    }).to_csv(C.TRUTH_DIR / "potential_outcomes.csv", index=False)

    print(f"Done in {time.time() - t0:.0f}s. Raw tables written to {C.RAW_DIR}")


if __name__ == "__main__":
    main()
