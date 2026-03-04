import os
import time
import json
import logging
from typing import Dict, Any, List, Iterable, Tuple, Optional

import requests

from dotenv import load_dotenv
load_dotenv()

PRODUCTS_URL = "https://api.btswholesaler.com/v1/api/getListProducts"
STOCK_URL = "https://api.btswholesaler.com/v1/api/getProductStock"

DEFAULT_PAGE_SIZE = 200
STOCK_BATCH_SIZE = 100
HTTP_TIMEOUT_SECONDS = 60


def chunked(items: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def get_token() -> str:
    token = os.getenv("BTS_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing BTS_API_TOKEN env var. "
            "Set it like: export BTS_API_TOKEN='...'"
        )
    return token


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def get_products_page(
    session: requests.Session, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
) -> Dict[str, Any]:
    params = {"page": page, "page_size": page_size}
    r = session.get(PRODUCTS_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def get_stock_for_eans(session: requests.Session, eans: List[str], verbose: bool = False) -> Dict[str, Any]:
    if not eans:
        return {}

    # BTS expects array param: product_sku[]=EAN1&product_sku[]=EAN2...
    params: List[Tuple[str, str]] = [("product_sku[]", e) for e in eans]
    r = session.get(STOCK_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()

    data = r.json()
    if verbose:
        logging.info(
            "Stock lookup requested=%s found=%s",
            data.get("requested_skus"),
            data.get("found_skus"),
        )

    return data.get("products", {}) or {}


def merge_preview(products: List[Dict[str, Any]], stock_map: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for p in products[:limit]:
        ean = p.get("ean")
        rt = stock_map.get(ean, {}) if ean else {}
        merged.append(
            {
                "ean": ean,
                "name": p.get("name"),
                "manufacturer": p.get("manufacturer"),
                "image": p.get("image"),
                "recommended_price": p.get("recommended_price"),
                "list_price": p.get("price"),
                "stock_list": p.get("stock"),
                "stock_realtime": rt.get("stock"),
                "price_realtime": rt.get("price"),
                "availability": rt.get("availability"),
            }
        )
    return merged


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    token = get_token()
    session = make_session(token)

    data = get_products_page(session, page=1, page_size=DEFAULT_PAGE_SIZE)
    products: List[Dict[str, Any]] = data.get("products", [])
    eans = [p["ean"] for p in products if p.get("ean")]

    logging.info("Fetched %s products on page 1 (EANs: %s)", len(products), len(eans))

    stock_map: Dict[str, Any] = {}
    for i, ean_batch in enumerate(chunked(eans, STOCK_BATCH_SIZE), start=1):
        logging.info(
            "Stock batch %s: size=%s first=%s last=%s",
            i,
            len(ean_batch),
            ean_batch[0],
            ean_batch[-1],
        )
        batch_stock = get_stock_for_eans(session, ean_batch, verbose=True)
        stock_map.update(batch_stock)

        # Optional: be nice to the API if needed later
        # time.sleep(0.1)

    preview = merge_preview(products, stock_map, limit=5)
    print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()