from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

DAG_TIMEZONE = pendulum.timezone("America/Los_Angeles")
PROJECT_ROOT = Path(
    os.getenv("GPU_PRICE_PROJECT_ROOT", Path(__file__).resolve().parents[1])
)
WORKBOOK_PATH = Path(
    os.getenv(
        "GPU_PRICE_WORKBOOK",
        PROJECT_ROOT / "算力价格爬虫数据整理.xlsx",
    )
)
OUTPUT_DIR = Path(os.getenv("GPU_PRICE_OUTPUT_DIR", PROJECT_ROOT / "output"))


with DAG(
    dag_id="daily_gpu_prices",
    description="Collect the public GPU prices defined in the source workbook.",
    schedule="0 21 * * *",
    start_date=pendulum.datetime(2026, 10, 26, tz=DAG_TIMEZONE),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={
        "owner": "data",
        "depends_on_past": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["gpu-prices", "daily"],
    doc_md="""
    Runs all supplier collectors daily at 9:00 PM America/Los_Angeles.

    The output date is derived from the data interval end in the DAG timezone,
    rather than Airflow's UTC process clock. Configure `GPU_PRICE_WORKBOOK`,
    `GPU_PRICE_OUTPUT_DIR`, and `GPU_PRICES_ALLOW_READ_PROXY` in the scheduler
    and worker environment when their defaults are not appropriate.
    """,
) as dag:
    collect_gpu_prices = BashOperator(
        task_id="collect_gpu_prices",
        bash_command="""
        set -euo pipefail
        cd "$GPU_PRICE_PROJECT_ROOT"
        python3 -m gpu_prices.collect \
          --workbook "$GPU_PRICE_WORKBOOK" \
          --output-dir "$GPU_PRICE_OUTPUT_DIR" \
          --run-date "{{ data_interval_end.in_timezone('America/Los_Angeles').strftime('%Y%m%d') }}" \
          --strict
        """,
        env={
            "GPU_PRICE_PROJECT_ROOT": str(PROJECT_ROOT),
            "GPU_PRICE_WORKBOOK": str(WORKBOOK_PATH),
            "GPU_PRICE_OUTPUT_DIR": str(OUTPUT_DIR),
            "GPU_PRICES_ALLOW_READ_PROXY": os.getenv(
                "GPU_PRICES_ALLOW_READ_PROXY", "true"
            ),
        },
        append_env=True,
        execution_timeout=timedelta(minutes=30),
        do_xcom_push=False,
    )
