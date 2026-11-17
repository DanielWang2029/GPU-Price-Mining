from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from gpu_prices.workbook import OUTPUT_HEADERS as DETAIL_COLUMNS
from gpu_prices.workbook import iso_date, make_record_id

SOURCE_LABEL = "price_mining"
GPU_SPECS = {
    "MI300X": {
        "gpu_id": "amd-mi300x",
        "vram_gb": 192,
        "interconnect_gbps": 896,
        "memory_bandwidth_gbps": 5300,
    },
    "MI325X": {
        "gpu_id": "amd-mi325x",
        "vram_gb": 256,
        "interconnect_gbps": 896,
        "memory_bandwidth_gbps": 6000,
    },
    "MI355X": {
        "gpu_id": "amd-mi355x",
        "vram_gb": 288,
        "interconnect_gbps": 1075,
        "memory_bandwidth_gbps": 8000,
    },
}


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider_id: str
    provider_name: str
    website: str
    country: str
    region: str
    supplier_type: str
    confidence: str = "review"


PROVIDERS = {
    "bentaus": ProviderMetadata(
        "bentaus", "Bentaus", "https://www.bentaus.com", "US", "North America",
        "GPU Cloud",
    ),
    "cirrascale": ProviderMetadata(
        "cirrascale", "Cirrascale", "https://www.cirrascale.com", "US",
        "North America", "GPU Cloud",
    ),
    "coregpu": ProviderMetadata(
        "coregpu", "CoreGPU", "https://coregpu.io", "US", "North America",
        "GPU Cloud",
    ),
    "cyfuture": ProviderMetadata(
        "cyfuture", "Cyfuture AI", "https://cyfuture.ai", "IN", "Asia-Pacific",
        "GPU Cloud",
    ),
    "daytona": ProviderMetadata(
        "daytona", "Daytona", "https://www.daytona.io", "US", "North America",
        "Serverless",
    ),
    "digitalocean": ProviderMetadata(
        "digitalocean", "DigitalOcean", "https://www.digitalocean.com", "US",
        "North America", "General Cloud & Hosting",
    ),
    "gpubank": ProviderMetadata(
        "gpubank", "GPUBank", "https://gpubank.io", "", "", "Unclassified",
        "low",
    ),
    "hotaisle": ProviderMetadata(
        "hotaisle", "Hot Aisle", "https://hotaisle.xyz", "US",
        "North America", "GPU Cloud",
    ),
    "impossible-cloud": ProviderMetadata(
        "impossible-cloud", "Impossible Cloud",
        "https://www.impossiblecloud.com", "DE", "Europe",
        "General Cloud & Hosting",
    ),
    "microsoft-azure": ProviderMetadata(
        "microsoft-azure", "Microsoft Azure", "https://azure.microsoft.com",
        "US", "North America", "Hyperscaler",
    ),
    "openrelay": ProviderMetadata(
        "openrelay", "OpenRelay", "https://openrelay.inc", "US",
        "North America", "GPU Cloud",
    ),
    "oracle-cloud": ProviderMetadata(
        "oracle-cloud", "Oracle Cloud", "https://www.oracle.com/cloud", "US",
        "North America", "Hyperscaler",
    ),
    "runcrate": ProviderMetadata(
        "runcrate", "Runcrate", "https://www.runcrate.ai", "US",
        "North America", "GPU Cloud",
    ),
    "runpod": ProviderMetadata(
        "runpod", "Runpod", "https://www.runpod.io", "US", "North America",
        "GPU Cloud",
    ),
    "tensorwave": ProviderMetadata(
        "tensorwave", "TensorWave", "https://tensorwave.com", "US",
        "North America", "GPU Cloud",
    ),
    "vultr": ProviderMetadata(
        "vultr", "Vultr", "https://www.vultr.com", "US", "North America",
        "General Cloud & Hosting",
    ),
}


@dataclass(frozen=True, slots=True)
class AmdOffer:
    provider_id: str
    gpu_model_code: str
    billing_type: str
    term_months: int
    raw_price: Decimal
    price_gpu_hour: Decimal
    gpu_count: int
    availability: str
    source_url: str
    gpu_spec: str = ""
    cpu_cores: Decimal | None = None
    system_ram_gb: Decimal | None = None
    disk_storage_gb: Decimal | None = None
    price_note: str = ""

    def __post_init__(self) -> None:
        if self.provider_id not in PROVIDERS:
            raise ValueError(f"Unknown AMD provider {self.provider_id!r}")
        if self.gpu_model_code not in GPU_SPECS:
            raise ValueError(f"Unknown AMD GPU model {self.gpu_model_code!r}")
        if self.gpu_count < 1:
            raise ValueError("GPU count must be positive")
        if self.billing_type == "RESERVATION":
            if self.term_months == 0:
                raise ValueError("Reservation term cannot be zero")
        elif self.term_months != 0:
            raise ValueError("Non-reservation term must be zero")
        if self.availability not in {"AVAILABLE", "UNAVAILABLE", "WAITLIST"}:
            raise ValueError(f"Invalid availability {self.availability!r}")


def _number(value: Decimal | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return format(value.normalize(), "f")


def detail_row(
    offer: AmdOffer,
    *,
    price_date: str,
    run_date: str,
) -> dict[str, str]:
    price_date = iso_date(price_date)
    run_date = iso_date(run_date)
    provider = PROVIDERS[offer.provider_id]
    gpu = GPU_SPECS[offer.gpu_model_code]
    raw_price = _number(offer.raw_price)
    price_gpu_hour = _number(offer.price_gpu_hour)
    vram = int(gpu["vram_gb"])
    gpu_id = str(gpu["gpu_id"])
    record_id = make_record_id(
        price_date=price_date,
        run_date=run_date,
        source_label=SOURCE_LABEL,
        provider=provider.provider_id,
        region_or_hq_country=provider.country or None,
        provider_hq_region=provider.region or None,
        gpu_id=gpu_id,
        billing=offer.billing_type,
        term_month=str(offer.term_months),
        raw_price=raw_price,
        price_gpu_hour=price_gpu_hour,
        availability=offer.availability,
    )
    return {
        "price_date": price_date,
        "run_date": run_date,
        "source_label": SOURCE_LABEL,
        "record_id": record_id,
        "publisher_name": provider.provider_name,
        "provider_id": provider.provider_id,
        "supplier_type": provider.supplier_type,
        "gpu_id": gpu_id,
        "gpu_model_code": offer.gpu_model_code,
        "gpu_count": str(offer.gpu_count),
        "gpu_spec": offer.gpu_spec,
        "vram_per_gpu_gb": str(vram),
        "vram_total_gb": str(vram * offer.gpu_count),
        "cpu_cores": _number(offer.cpu_cores),
        "system_ram_gb": _number(offer.system_ram_gb),
        "disk_storage_gb": _number(offer.disk_storage_gb),
        "interconnect_bandwidth_gbps": str(gpu["interconnect_gbps"]),
        "gpu_mem_bandwidth_gbps": str(gpu["memory_bandwidth_gbps"]),
        "billing_type": offer.billing_type,
        "term_months": str(offer.term_months),
        "region_or_hq_country": provider.country,
        "provider_hq_region": provider.region,
        "raw_price": raw_price,
        "price_gpu_hour": price_gpu_hour,
        "availability": offer.availability,
        "price_note": offer.price_note,
        "source_url": offer.source_url,
    }


def build_detail_rows(
    offers: Iterable[AmdOffer],
    *,
    price_date: str,
    run_date: str,
) -> tuple[list[dict[str, str]], list[tuple[str, str, str]]]:
    rows: list[dict[str, str]] = []
    duplicates: list[tuple[str, str, str]] = []
    by_record_id: dict[str, dict[str, str]] = {}
    for offer in offers:
        row = detail_row(offer, price_date=price_date, run_date=run_date)
        previous = by_record_id.get(row["record_id"])
        if previous is not None:
            duplicates.append(
                (
                    row["provider_id"],
                    previous["source_url"],
                    row["source_url"],
                )
            )
            continue
        by_record_id[row["record_id"]] = row
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["provider_id"],
            row["gpu_model_code"],
            row["billing_type"],
            int(row["term_months"]),
            int(row["gpu_count"]),
            Decimal(row["raw_price"]),
            row["source_url"],
        )
    )
    return rows, duplicates


def write_detail_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=DETAIL_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


NUMERIC_COLUMNS = {
    "gpu_count",
    "vram_per_gpu_gb",
    "vram_total_gb",
    "cpu_cores",
    "system_ram_gb",
    "disk_storage_gb",
    "interconnect_bandwidth_gbps",
    "gpu_mem_bandwidth_gbps",
    "term_months",
    "raw_price",
    "price_gpu_hour",
}


def _sql_value(column: str, value: str) -> str:
    if value == "":
        return "NULL"
    if column in NUMERIC_COLUMNS:
        Decimal(value)
        return value
    return "'" + value.replace("'", "''") + "'"


def render_detail_sql(rows: list[dict[str, str]]) -> str:
    if not rows:
        raise ValueError("No AMD detail rows to render")
    price_date = rows[0]["price_date"]
    if any(row["price_date"] != price_date for row in rows):
        raise ValueError("AMD SQL input spans multiple price dates")
    provider_ids = sorted({row["provider_id"] for row in rows})
    models = sorted({row["gpu_model_code"] for row in rows})
    providers_sql = ",".join(_sql_value("provider_id", item) for item in provider_ids)
    models_sql = ",".join(_sql_value("gpu_model_code", item) for item in models)
    columns = ",".join(DETAIL_COLUMNS)
    chunks = [
        "BEGIN;",
        "",
        "DELETE FROM public.compute_insight_gpu_price_detail_daily",
        f"WHERE source_label = '{SOURCE_LABEL}'",
        f"  AND price_date = '{price_date}'",
        f"  AND provider_id IN ({providers_sql})",
        f"  AND gpu_model_code IN ({models_sql});",
        "",
    ]
    for start in range(0, len(rows), 500):
        values = ",\n".join(
            "    ("
            + ",".join(_sql_value(column, row[column]) for column in DETAIL_COLUMNS)
            + ")"
            for row in rows[start : start + 500]
        )
        chunks.extend(
            [
                "INSERT INTO public.compute_insight_gpu_price_detail_daily "
                f"({columns}) VALUES",
                values + ";",
                "",
            ]
        )
    chunks.append("COMMIT;")
    return "\n".join(chunks) + "\n"


def render_provider_sql(
    provider_ids: Iterable[str],
    *,
    updated_at: str,
) -> str:
    providers = [PROVIDERS[provider_id] for provider_id in sorted(set(provider_ids))]
    values = ",\n".join(
        "    ("
        + ",".join(
            [
                _sql_value("provider_id", provider.provider_id),
                _sql_value("provider_name", provider.provider_name),
                _sql_value("website", provider.website),
                _sql_value("region_or_hq_country", provider.country),
                _sql_value("provider_hq_region", provider.region),
                _sql_value("supplier_type", provider.supplier_type),
                _sql_value("tier_confidence", provider.confidence),
                _sql_value("updated_at", updated_at),
            ]
        )
        + ")"
        for provider in providers
    )
    return f"""INSERT INTO public.compute_insight_dim_provider (
    provider_id,
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
)
SELECT
    values.provider_id,
    values.provider_name,
    values.website,
    values.region_or_hq_country,
    values.provider_hq_region,
    values.supplier_type,
    values.tier_confidence,
    values.updated_at::timestamp without time zone
FROM (VALUES
{values}
) AS values (
    provider_id,
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
)
WHERE NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider AS existing
    WHERE existing.provider_id = values.provider_id
);
"""
