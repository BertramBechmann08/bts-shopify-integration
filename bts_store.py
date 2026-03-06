import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OrderLink:
    external_id: str        # later: Shopify order id
    bts_order_number: str
    created_at: str


class JSONStore:
    """
    Minimal persistence for prototype:
    - data/order_map.json keeps mapping external_id -> bts_order_number
    """
    def __init__(self, path: str = "data/order_map.json") -> None:
        self.path = path

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"orders": {}}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, doc: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get_order_link(self, external_id: str) -> Optional[OrderLink]:
        doc = self._load()
        row = doc.get("orders", {}).get(external_id)
        if not row:
            return None
        return OrderLink(
            external_id=external_id,
            bts_order_number=row["bts_order_number"],
            created_at=row["created_at"],
        )

    def put_order_link(self, external_id: str, bts_order_number: str) -> None:
        doc = self._load()
        orders = doc.setdefault("orders", {})
        orders[external_id] = {
            "bts_order_number": bts_order_number,
            "created_at": utc_now_iso(),
        }
        self._save(doc)