import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OrderLink:
    external_id: str
    bts_order_number: str
    created_at: str


class JSONOrderStore:
    """
    Local persistence for order mappings:
    external_id -> BTS order number
    """

    def __init__(self, path: str = "data/order_map.json") -> None:
        self.path = Path(path)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"orders": {}}

        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, doc: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        tmp_path.replace(self.path)

    def get_order_link(self, external_id: str) -> Optional[OrderLink]:
        doc = self._load()
        row = doc.get("orders", {}).get(external_id)
        if not row:
            return None

        return OrderLink(
            external_id=external_id,
            bts_order_number=str(row["bts_order_number"]),
            created_at=row["created_at"],
        )

    def put_order_link(self, external_id: str, bts_order_number: str) -> None:
        doc = self._load()
        orders = doc.setdefault("orders", {})
        orders[external_id] = {
            "bts_order_number": str(bts_order_number),
            "created_at": utc_now_iso(),
        }
        self._save(doc)

    def list_external_ids(self) -> List[str]:
        doc = self._load()
        return list(doc.get("orders", {}).keys())

    def list_order_links(self) -> List[OrderLink]:
        links: List[OrderLink] = []

        for external_id in self.list_external_ids():
            link = self.get_order_link(external_id)
            if link is not None:
                links.append(link)

        return links