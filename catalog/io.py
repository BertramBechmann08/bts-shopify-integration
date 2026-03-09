import json
from typing import Any, Dict, List, Set


def load_snapshot(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Snapshot file must contain a JSON list")

    return data


def load_ean_allowlist(path: str) -> Set[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    allowed: Set[str] = set()
    for line in lines:
        value = line.strip()
        if value and not value.startswith("#"):
            allowed.add(value)

    return allowed


def load_brand_allowlist(path: str) -> Set[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    allowed: Set[str] = set()
    for line in lines:
        value = line.strip()
        if value and not value.startswith("#"):
            allowed.add(value.upper())

    return allowed