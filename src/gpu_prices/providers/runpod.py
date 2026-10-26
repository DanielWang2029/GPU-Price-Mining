from __future__ import annotations

from datetime import datetime

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import run_provider_cli

URL = "https://api.runpod.io/graphql"
QUERY = """
query {
  gpuTypes {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    securePrice
    communityPrice
  }
}
"""
GPU_IDS = {
    "B300": "NVIDIA B300 SXM6 AC",
    "H200": "NVIDIA H200",
    "B200": "NVIDIA B200",
    "A100": "NVIDIA A100 80GB PCIe",
}


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.post_json(
        URL,
        json={"query": QUERY},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    if payload.get("errors"):
        raise ValueError(f"RunPod GraphQL returned errors: {payload['errors']}")
    catalog = {item["id"]: item for item in payload.get("data", {}).get("gpuTypes", [])}
    observations: list[Observation] = []
    for row in rows:
        gpu_id = GPU_IDS[row.gpu_model_code]
        item = catalog.get(gpu_id)
        if item is None:
            raise ValueError(f"RunPod catalog omitted {gpu_id}")
        community = row.cloud_type == "Community"
        supported = item["communityCloud" if community else "secureCloud"]
        raw = item["communityPrice" if community else "securePrice"]
        if not supported or raw in (None, 0):
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=f"RunPod does not currently list {gpu_id} in {row.cloud_type}.",
                )
            )
            continue
        observations.append(
            ok(
                row,
                raw,
                fetched_at=now,
                source_url=URL,
                raw_value=str(raw),
                note=(
                    f"Published {row.cloud_type} Cloud on-demand list price "
                    "in USD per GPU-hour."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("RunPod")
