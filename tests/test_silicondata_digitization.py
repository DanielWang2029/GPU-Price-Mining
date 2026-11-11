from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.digitize_silicondata_curves import (
    CONFIGS,
    PLOT_X_END,
    PLOT_X_START,
    estimate_curve,
    extract_centerline,
    read_png,
    reconstruction_metrics,
    reference_metrics,
    write_provider_series_sql,
)

ROOT = Path(__file__).resolve().parents[1]


class SiliconDataDigitizationTests(unittest.TestCase):
    def test_digitized_curves_match_image_and_labeled_anchors(self) -> None:
        expected_rows = {"B300": 202, "B200": 467, "H200": 191}
        image_mae_limits = {"B300": 0.005, "B200": 0.006, "H200": 0.003}
        history_mae_limits = {"B300": 0.005, "B200": 0.020, "H200": 0.005}
        reference = ROOT / "output/gpu_prices_history_20261001_20261108.csv"
        all_estimates: dict[str, list[tuple[date, float]]] = {}

        for config in CONFIGS:
            with self.subTest(model=config.model):
                raster = read_png(ROOT / "images" / config.image_name)
                centerline, candidates = extract_centerline(raster)
                estimates, start_y, end_y = estimate_curve(config, centerline)
                all_estimates[config.model] = estimates
                by_date = dict(estimates)

                self.assertEqual(len(estimates), expected_rows[config.model])
                self.assertEqual(by_date[config.start_date], config.start_price)
                self.assertEqual(by_date[config.end_date], config.end_price)
                self.assertEqual(by_date[config.low_date], config.low_price)
                self.assertEqual(by_date[config.high_date], config.high_price)
                self.assertTrue(
                    all(
                        config.low_price <= price <= config.high_price
                        and price == round(price, 2)
                        for _, price in estimates
                    )
                )
                self.assertGreater(
                    len(candidates),
                    (PLOT_X_END - PLOT_X_START) * 0.9,
                )

                image_metrics = reconstruction_metrics(
                    config,
                    estimates,
                    start_y,
                    end_y,
                    centerline,
                    candidates,
                )
                self.assertLess(
                    image_metrics["mean_absolute_error"],
                    image_mae_limits[config.model],
                )
                saved_metrics = reference_metrics(
                    reference,
                    config.model,
                    estimates,
                )
                self.assertIsNotNone(saved_metrics)
                assert saved_metrics is not None
                self.assertLess(
                    saved_metrics["mean_absolute_error"],
                    history_mae_limits[config.model],
                )

        with TemporaryDirectory() as temporary:
            sql_path = Path(temporary) / "provider_series.sql"
            write_provider_series_sql(
                sql_path,
                all_estimates,
                run_date=date(2026, 11, 10),
            )
            sql = sql_path.read_text(encoding="utf-8")
        self.assertIn(
            "DELETE FROM public.compute_insight_gpu_provider_series_daily",
            sql,
        )
        self.assertNotIn("public.public.", sql)
        self.assertEqual(sql.count("INSERT INTO "), 2)
        self.assertEqual(
            sql.count(
                "'https://portal.silicondata.com/silicon-index','GPU INDEX'"
            ),
            860,
        )
        self.assertIn(
            "('2025-08-01','2026-11-10','nvidia-b200','B200',"
            "'ON_DEMAND',0,'silicondata',5.31,1,'GPU Cloud'",
            sql,
        )
        self.assertIn(
            "('2026-11-10','2026-11-10','nvidia-h200','H200',"
            "'ON_DEMAND',0,'silicondata',3.48,1,'GPU Cloud'",
            sql,
        )


if __name__ == "__main__":
    unittest.main()
