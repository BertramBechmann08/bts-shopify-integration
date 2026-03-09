import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProductLink:
    ean: str
    shopify_product_id: int
    shopify_variant_id: int
    shopify_inventory_item_id: int
    created_at: str
    updated_at: str


class JSONProductStore:
    """
    Local persistence for product mappings:
    BTS EAN -> Shopify product / variant / inventory item IDs
    """

    def __init__(self, path: str = "data/product_map.json") -> None:
        self.path = Path(path)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"products": {}}

        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, doc: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        tmp_path.replace(self.path)

    def get_product_link(self, ean: str) -> Optional[ProductLink]:
        doc = self._load()
        row = doc.get("products", {}).get(ean)
        if not row:
            return None

        return ProductLink(
            ean=ean,
            shopify_product_id=int(row["shopify_product_id"]),
            shopify_variant_id=int(row["shopify_variant_id"]),
            shopify_inventory_item_id=int(row["shopify_inventory_item_id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def put_product_link(
        self,
        ean: str,
        shopify_product_id: int,
        shopify_variant_id: int,
        shopify_inventory_item_id: int,
    ) -> None:
        doc = self._load()
        products = doc.setdefault("products", {})

        existing = products.get(ean)
        created_at = existing["created_at"] if existing else utc_now_iso()

        products[ean] = {
            "shopify_product_id": int(shopify_product_id),
            "shopify_variant_id": int(shopify_variant_id),
            "shopify_inventory_item_id": int(shopify_inventory_item_id),
            "created_at": created_at,
            "updated_at": utc_now_iso(),
        }

        self._save(doc)

    def list_eans(self) -> List[str]:
        doc = self._load()
        return list(doc.get("products", {}).keys())

    def list_product_links(self) -> List[ProductLink]:
        links: List[ProductLink] = []

        for ean in self.list_eans():
            link = self.get_product_link(ean)
            if link is not None:
                links.append(link)

        return links