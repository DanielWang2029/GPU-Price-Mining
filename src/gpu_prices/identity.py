from __future__ import annotations

import re

PUBLISHER_NAMES = {
    "SiliconData": "Silicon Data",
}
PROVIDER_IDS = {
    "Compute Desk": "compute-desk",
}
PROVIDER_ID_ALIASES = {
    "computedesk": "compute-desk",
}


def publisher_name(name: str) -> str:
    return PUBLISHER_NAMES.get(name, name)


def provider_id(name: str) -> str:
    publisher = publisher_name(name)
    return PROVIDER_IDS.get(publisher, re.sub(r"[^a-z]", "", publisher.lower()))


def canonicalize_provider_id(value: str) -> str:
    return PROVIDER_ID_ALIASES.get(value, value)
