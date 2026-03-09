import math
import os
from typing import Any, Dict


def parse_price_value(raw: Any) -> float:
    if raw in (None, ""):
        return 0.0

    text = str(raw).strip()
    text = text.replace("€", "").replace("EUR", "").strip()
    text = text.replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def retail_round_dkk(price_dkk: float) -> float:
    if price_dkk <= 0:
        return 0.0

    rounded = math.floor(price_dkk / 10.0) * 10.0 - 1.0
    if rounded <= 0:
        rounded = max(1.0, math.floor(price_dkk) - 1.0)
    return rounded


def choose_source_price_eur(product: Dict[str, Any]) -> float:
    source = os.getenv("SHOPIFY_PRICE_SOURCE", "price_realtime").strip()

    if source == "recommended_price":
        candidates = [
            product.get("recommended_price"),
            product.get("price_realtime"),
            product.get("list_price"),
        ]
    elif source == "list_price":
        candidates = [
            product.get("list_price"),
            product.get("price_realtime"),
            product.get("recommended_price"),
        ]
    else:
        candidates = [
            product.get("price_realtime"),
            product.get("list_price"),
            product.get("recommended_price"),
        ]

    for raw in candidates:
        value = parse_price_value(raw)
        if value > 0:
            return value

    return 0.0


def choose_price(product: Dict[str, Any]) -> str:
    eur_to_dkk = float(os.getenv("SHOPIFY_PRICE_EUR_TO_DKK", "7.45"))
    markup = float(os.getenv("SHOPIFY_PRICE_MARKUP", "2.0"))
    vat_rate = float(os.getenv("SHOPIFY_PRICE_VAT_RATE", "1.25"))
    enable_rounding = os.getenv("SHOPIFY_ENABLE_RETAIL_ROUNDING", "1").strip() == "1"

    source_price_eur = choose_source_price_eur(product)
    price_dkk = source_price_eur * eur_to_dkk * markup * vat_rate

    if enable_rounding:
        price_dkk = retail_round_dkk(price_dkk)

    return f"{price_dkk:.2f}"