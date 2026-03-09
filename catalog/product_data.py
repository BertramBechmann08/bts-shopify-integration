from typing import Any, Dict


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def parse_stock(product: Dict[str, Any]) -> int:
    raw = product.get("stock_realtime")
    if raw in (None, ""):
        raw = product.get("stock_list", 0)

    try:
        stock = int(raw)
    except (TypeError, ValueError):
        stock = 0

    return max(stock, 0)