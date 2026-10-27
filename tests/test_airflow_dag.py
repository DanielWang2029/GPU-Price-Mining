from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAG_PATH = ROOT / "dags" / "gpu_prices_daily.py"


class AirflowDagTests(unittest.TestCase):
    def test_daily_dag_uses_local_run_date_and_strict_collection(self) -> None:
        source = DAG_PATH.read_text(encoding="utf-8")
        ast.parse(source)

        self.assertIn('schedule="0 21 * * *"', source)
        self.assertIn('"America/Los_Angeles"', source)
        self.assertIn("catchup=False", source)
        self.assertIn("max_active_runs=1", source)
        self.assertIn("data_interval_end.in_timezone", source)
        self.assertIn("--strict", source)


if __name__ == "__main__":
    unittest.main()
