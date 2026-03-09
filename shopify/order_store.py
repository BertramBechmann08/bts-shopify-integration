import json
from pathlib import Path


class JSONOrderStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self._save({"orders": {}})

    def _load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def has_order(self, shopify_order_id: str) -> bool:
        data = self._load()
        return str(shopify_order_id) in data.get("orders", {})

    def store_order(self, shopify_order_id: str, bts_order_id: str):
        data = self._load()
        data.setdefault("orders", {})
        data["orders"][str(shopify_order_id)] = str(bts_order_id)
        self._save(data)