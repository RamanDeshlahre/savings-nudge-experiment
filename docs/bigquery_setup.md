# Running the dbt models on BigQuery

The project runs locally on SQLite by default (`python src/run_all.py`). This guide runs the same dbt models on Google BigQuery. The free sandbox is enough, and you don't need a credit card.

## 1. Create a project and datasets

1. Go to the BigQuery console and create a project, for example `savings-nudge-demo`.
2. Create two datasets in location EU: `raw` (source tables) and `analytics` (dbt output).

## 2. Generate and upload the raw data

```bash
python src/01_simulate_data.py

for t in customers assignments exposures pre_period_activity salary_events pot_events monthly_activity weekly_pot_transfers; do
  bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
    raw.$t data/raw/$t.csv
done
```

You can also upload each CSV through the console with *Create table → Upload*.

## 3. Install dbt and connect

```bash
pip install dbt-bigquery
gcloud auth application-default login
cp dbt/profiles.yml.example ~/.dbt/profiles.yml   # then set your project id
```

## 4. Build and test

```bash
cd dbt
dbt build          # runs every model and every test in schema.yml and tests/
dbt docs generate && dbt docs serve   # optional: lineage graph for your README
```

The models use only portable SQL: no engine-specific date or math functions. That's why the same files run on BigQuery and in the local SQLite runner.

## 5. Point the analysis at BigQuery (optional)

The Python analysis reads from SQLite through `analysis_utils.query()`. To read from BigQuery instead, replace that function with:

```python
from google.cloud import bigquery
client = bigquery.Client()

def query(sql):
    sql = sql.replace("from fct_", "from analytics.fct_").replace("from agg_", "from analytics.agg_")
    return client.query(sql).to_dataframe()
```

Then run `pip install google-cloud-bigquery db-dtypes`.
