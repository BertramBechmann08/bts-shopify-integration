import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

PRODUCTS_URL = "https://api.btswholesaler.com/v1/api/getListProducts"
PRODUCT_CHANGES_URL = "https://api.btswholesaler.com/v1/api/getProductChanges"
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
        raise RuntimeError("Missing BTS_API_TOKEN env var. Put it in .env as BTS_API_TOKEN=...")
    return token


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def get_products_page(
    session: requests.Session,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    params = {"page": page, "page_size": page_size}
    r = session.get(PRODUCTS_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def get_product_changes_page(
    session: requests.Session,
    since: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    params = {
        "since": since,
        "page": page,
        "page_size": page_size,
    }
    r = session.get(PRODUCT_CHANGES_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def fetch_products(
    session: requests.Session,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    all_products: List[Dict[str, Any]] = []
    page = 1

    while True:
        data = get_products_page(session, page=page, page_size=page_size)
        products = data.get("products", []) or []
        pagination = data.get("pagination", {}) or {}

        all_products.extend(products)
        logging.info(
            "Fetched catalog page %s: %s products (total so far: %s)",
            page,
            len(products),
            len(all_products),
        )

        if max_pages is not None and page >= max_pages:
            logging.info("Stopping early at max_pages=%s", max_pages)
            break

        if not pagination.get("has_next_page"):
            break

        page += 1

    return all_products


def fetch_product_changes(
    session: requests.Session,
    since: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    all_products: List[Dict[str, Any]] = []
    page = 1

    while True:
        data = get_product_changes_page(session, since=since, page=page, page_size=page_size)
        products = data.get("products", []) or []
        pagination = data.get("pagination", {}) or {}

        all_products.extend(products)
        logging.info(
            "Fetched changes page %s: %s products changed since %s (total so far: %s)",
            page,
            len(products),
            since,
            len(all_products),
        )

        if max_pages is not None and page >= max_pages:
            logging.info("Stopping early at max_pages=%s", max_pages)
            break

        if not pagination.get("has_next_page"):
            break

        page += 1

    return all_products


def get_stock_for_eans(session: requests.Session, eans: List[str]) -> Dict[str, Any]:
    if not eans:
        return {}

    params: List[Tuple[str, str]] = [("product_sku[]", e) for e in eans]
    r = session.get(STOCK_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json() or {}
    return data.get("products", {}) or {}


def build_full_snapshot(products: List[Dict[str, Any]], stock_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    snapshot: List[Dict[str, Any]] = []

    for p in products:
        ean = p.get("ean")
        rt = stock_map.get(ean, {}) if ean else {}

        snapshot.append(
            {
                "id": p.get("id"),
                "ean": ean,
                "name": p.get("name"),
                "manufacturer": p.get("manufacturer"),
                "categories": p.get("categories"),
                "image": p.get("image"),
                "recommended_price": p.get("recommended_price"),
                "list_price": p.get("price"),
                "stock_list": p.get("stock"),
                "leadtime_to_ship": p.get("leadtime_to_ship"),
                "flammable": p.get("flammable"),
                "restricted_countries": p.get("restricted_countries"),
                "stock_realtime": rt.get("stock"),
                "price_realtime": rt.get("price"),
                "availability": rt.get("availability"),
                "last_updated": rt.get("last_updated"),
            }
        )

    return snapshot


def build_delta_snapshot(products: List[Dict[str, Any]], stock_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    snapshot: List[Dict[str, Any]] = []

    for p in products:
        ean = p.get("product_sku")
        rt = stock_map.get(ean, {}) if ean else {}

        snapshot.append(
            {
                "id": p.get("id"),
                "ean": ean,
                "last_modified": p.get("last_modified"),
                "recommended_price": p.get("recommended_price"),
                "list_price_changed": p.get("product_price"),
                "stock_changed": p.get("product_stock"),
                "stock_realtime": rt.get("stock"),
                "price_realtime": rt.get("price"),
                "availability": rt.get("availability"),
                "last_updated": rt.get("last_updated"),
            }
        )

    return snapshot


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def report(snapshot: List[Dict[str, Any]]) -> None:
    total = len(snapshot)
    in_stock = sum(1 for x in snapshot if (x.get("stock_realtime") or 0) > 0)
    logging.info("Report: total_products=%s in_stock=%s", total, in_stock)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["full", "delta"],
        default="full",
        help="full = full catalog sync, delta = getProductChanges sync",
    )
    parser.add_argument(
        "--since",
        type=str,
        default="",
        help='Required for delta mode. Example: "2026-03-01" or "2026-03-01 00:00:00"',
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Products per page (50-500 recommended by BTS)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page cap for testing",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output path. If omitted, saves to data/ with timestamp",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = make_session(get_token())

    if args.mode == "full":
        products = fetch_products(
            session,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
        eans = [p["ean"] for p in products if p.get("ean")]
        logging.info("Full catalog loaded: products=%s eans=%s", len(products), len(eans))

        stock_map: Dict[str, Any] = {}
        for i, ean_batch in enumerate(chunked(eans, STOCK_BATCH_SIZE), start=1):
            logging.info(
                "Stock batch %s: size=%s first=%s last=%s",
                i,
                len(ean_batch),
                ean_batch[0],
                ean_batch[-1],
            )
            batch_stock = get_stock_for_eans(session, ean_batch)
            stock_map.update(batch_stock)

        logging.info("Stock map built: %s entries", len(stock_map))

        snapshot = build_full_snapshot(products, stock_map)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = args.output or f"data/bts_snapshot_full_{ts}.json"

    else:
        if not args.since.strip():
            raise RuntimeError("--since is required when --mode delta")

        products = fetch_product_changes(
            session,
            since=args.since.strip(),
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
        eans = [p["product_sku"] for p in products if p.get("product_sku")]
        logging.info("Delta sync loaded: changed_products=%s eans=%s", len(products), len(eans))

        stock_map: Dict[str, Any] = {}
        for i, ean_batch in enumerate(chunked(eans, STOCK_BATCH_SIZE), start=1):
            logging.info(
                "Delta stock batch %s: size=%s first=%s last=%s",
                i,
                len(ean_batch),
                ean_batch[0],
                ean_batch[-1],
            )
            batch_stock = get_stock_for_eans(session, ean_batch)
            stock_map.update(batch_stock)

        logging.info("Delta stock map built: %s entries", len(stock_map))

        snapshot = build_delta_snapshot(products, stock_map)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = args.output or f"data/bts_snapshot_delta_{ts}.json"

    report(snapshot)
    save_json(out_path, snapshot)
    logging.info("Saved snapshot to %s", out_path)

    print(json.dumps(snapshot[:5], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()