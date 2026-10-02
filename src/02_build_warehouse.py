"""
STEP 2 - Build the warehouse (load raw data, run the dbt models, run tests).

In production this project runs on BigQuery with dbt:
    dbt build --project-dir dbt          (see docs/bigquery_setup.md)

So that anyone can run it on a laptop with no cloud account, this script is a
small "mini-dbt" that runs the SAME model SQL files against a local SQLite
database. It:
  1. loads data/raw/*.csv into tables named raw_<name>
  2. resolves {{ ref() }}, {{ source() }} and {{ var() }} in each model
  3. builds models in dependency order (staging = views, marts = tables)
  4. runs the tests declared in schema.yml plus the singular tests in dbt/tests

The SQL is written to be portable (no engine-specific date or math functions).
"""
import re
import sqlite3
import time

import pandas as pd
import yaml

import config as C

REF_RE = re.compile(r"\{\{\s*ref\(\s*'(\w+)'\s*\)\s*\}\}")
SOURCE_RE = re.compile(r"\{\{\s*source\(\s*'(\w+)'\s*,\s*'(\w+)'\s*\)\s*\}\}")
VAR_RE = re.compile(r"\{\{\s*var\(\s*'(\w+)'\s*\)\s*\}\}")

INDEXES = {
    "raw_customers": ["user_id"],
    "raw_assignments": ["user_id"],
    "raw_exposures": ["user_id"],
    "raw_pre_period_activity": ["user_id"],
    "raw_salary_events": ["user_id"],
    "raw_pot_events": ["user_id"],
    "raw_monthly_activity": ["user_id, month_number", "month_number"],
    "raw_weekly_pot_transfers": ["user_id"],
}


def load_raw(con):
    for csv in sorted(C.RAW_DIR.glob("*.csv")):
        table = f"raw_{csv.stem}"
        con.execute(f"drop table if exists {table}")
        for i, chunk in enumerate(pd.read_csv(csv, chunksize=500_000)):
            chunk.to_sql(table, con, if_exists="append" if i else "replace", index=False)
        for cols in INDEXES.get(table, []):
            name = f"ix_{table}_{cols.replace(', ', '_')}"
            con.execute(f"create index {name} on {table} ({cols})")
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  loaded {table:<28} {n:>10,} rows")
    con.commit()


def check_vars_match_config(dbt_vars):
    expected = {
        "interchange_rate": C.INTERCHANGE_RATE,
        "current_account_margin": C.CURRENT_ACCOUNT_MARGIN,
        "savings_margin": C.SAVINGS_MARGIN,
        "cost_to_serve_monthly": C.COST_TO_SERVE_MONTHLY,
        "cost_per_support_contact": C.COST_PER_SUPPORT_CONTACT,
    }
    for k, v in expected.items():
        if abs(float(dbt_vars[k]) - v) > 1e-12:
            raise ValueError(f"dbt var {k}={dbt_vars[k]} does not match config.py ({v})")


def render(sql, dbt_vars):
    sql = REF_RE.sub(lambda m: m.group(1), sql)
    sql = SOURCE_RE.sub(lambda m: f"{m.group(1)}_{m.group(2)}", sql)
    sql = VAR_RE.sub(lambda m: str(dbt_vars[m.group(1)]), sql)
    return sql


def topo_sort(models):
    deps = {name: set(REF_RE.findall(info["sql"])) for name, info in models.items()}
    order, done = [], set()

    def visit(node, stack=()):
        if node in done:
            return
        if node in stack:
            raise ValueError(f"cycle at {node}")
        for d in deps[node]:
            visit(d, stack + (node,))
        done.add(node)
        order.append(node)

    for name in sorted(models):
        visit(name)
    return order


def build_models(con, dbt_vars, project):
    mats = project["models"]["savings_nudge"]
    models = {}
    for folder in ["staging", "marts"]:
        for f in (C.DBT_DIR / "models" / folder).glob("*.sql"):
            models[f.stem] = {"sql": f.read_text(), "mat": mats[folder]["+materialized"]}
    for name in topo_sort(models):
        t = time.time()
        info = models[name]
        sql = render(info["sql"], dbt_vars)
        con.execute(f"drop view if exists {name}")
        con.execute(f"drop table if exists {name}")
        con.execute(f"create {info['mat']} {name} as {sql}")
        if name == "fct_experiment_users":
            con.execute("create index ix_feu_user on fct_experiment_users (user_id)")
        if name == "fct_user_monthly_value":
            con.execute("create index ix_fumv_user_month on fct_user_monthly_value (user_id, month_number)")
        print(f"  built {info['mat']:<5} {name:<28} ({time.time() - t:.1f}s)")
    con.commit()


def run_tests(con, dbt_vars):
    failures = 0
    schema = yaml.safe_load((C.DBT_DIR / "models" / "marts" / "schema.yml").read_text())
    for model in schema["models"]:
        for col in model.get("columns", []):
            for test in col.get("tests", []):
                if test == "unique":
                    q = (f"select count(*) from (select {col['name']} from {model['name']} "
                         f"group by {col['name']} having count(*) > 1)")
                    label = "unique"
                elif test == "not_null":
                    q = f"select count(*) from {model['name']} where {col['name']} is null"
                    label = "not_null"
                elif isinstance(test, dict) and "accepted_values" in test:
                    vals = ", ".join(f"'{v}'" for v in test["accepted_values"]["values"])
                    q = f"select count(*) from {model['name']} where {col['name']} not in ({vals})"
                    label = "accepted_values"
                else:
                    continue
                bad = con.execute(q).fetchone()[0]
                status = "PASS" if bad == 0 else f"FAIL ({bad} rows)"
                failures += bad > 0
                print(f"  test {label:<16} {model['name']}.{col['name']:<22} {status}")
    for f in sorted((C.DBT_DIR / "tests").glob("*.sql")):
        sql = render(f.read_text(), dbt_vars)
        bad = con.execute(f"select count(*) from ({sql})").fetchone()[0]
        status = "PASS" if bad == 0 else f"FAIL ({bad} rows)"
        failures += bad > 0
        print(f"  test {'singular':<16} {f.stem:<45} {status}")
    if failures:
        raise SystemExit(f"{failures} data test(s) failed")


def main():
    t0 = time.time()
    project = yaml.safe_load((C.DBT_DIR / "dbt_project.yml").read_text())
    dbt_vars = project["vars"]
    check_vars_match_config(dbt_vars)

    if C.WAREHOUSE.exists():
        C.WAREHOUSE.unlink()
    con = sqlite3.connect(C.WAREHOUSE)
    con.execute("pragma journal_mode = off")
    con.execute("pragma synchronous = off")

    print("Loading raw data...")
    load_raw(con)
    print("Building models...")
    build_models(con, dbt_vars, project)
    print("Running data tests...")
    run_tests(con, dbt_vars)
    con.close()
    print(f"Warehouse ready at {C.WAREHOUSE} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
