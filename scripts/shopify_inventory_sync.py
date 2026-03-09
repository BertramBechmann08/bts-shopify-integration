import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv

from catalog.filters import product_matches_filters
from catalog.io import load_brand_allowlist, load_ean_allowlist, load_snapshot
from catalog.product_data import clean_text, parse_stock
from shopify.client import ShopifyClient
from shopify.store import JSONProductStore

load_dotenv()


def build_snapshot_index(snapshot: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for product in snapshot:
        ean = clean_text(product.get("ean"))
        if ean:
            indexed[ean] = product
    return indexed


def select_subset_eans(
    snapshot: List[Dict[str, Any]],
    mapped_eans: Set[str],
    limit: int,
    require_ean: bool = True,
    brand_filter: Optional[str] = None,
    min_stock: int = 0,
    allowed_eans: Optional[Set[str]] = None,
    allowed_brands: Optional[Set[str]] = None,
) -> List[str]:
    selected: List[str] = []

    for product in snapshot:
        ean = clean_text(product.get("ean"))
        if not ean or ean not in mapped_eans:
            continue

        if not product_matches_filters(
            product=product,
            require_image=False,
            require_ean=require_ean,
            brand_filter=brand_filter,
            min_stock=min_stock,
            allowed_eans=allowed_eans,
            allowed_brands=allowed_brands,
        ):
            continue

        selected.append(ean)

        if limit > 0 and len(selected) >= limit:
            break

    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="Path to BTS snapshot JSON")
    parser.add_argument("--product-map", default="data/product_map.json", help="Path to local product mapping JSON")
    parser.add_argument("--limit", type=int, default=0, help="Number of products to sync (0 = no limit)")
    parser.add_argument("--commit", action="store_true", help="Actually update inventory in Shopify")

    parser.add_argument("--brand", type=str, default="", help="Only sync products from this manufacturer/brand")
    parser.add_argument("--brand-file", type=str, default="", help="Optional file containing one allowed brand per line")
    parser.add_argument("--ean-file", type=str, default="", help="Optional file containing one allowed EAN per line")
    parser.add_argument("--min-stock", type=int, default=0, help="Only sync products with stock >= this value")
    parser.add_argument("--allow-no-ean", action="store_true", help="Allow products without EAN")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    location_id_raw = os.getenv("SHOPIFY_LOCATION_ID", "").strip()
    if not location_id_raw:
        raise RuntimeError("Missing SHOPIFY_LOCATION_ID in environment")
    location_id = int(location_id_raw)

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")

    snapshot = load_snapshot(str(snapshot_path))
    snapshot_by_ean = build_snapshot_index(snapshot)

    client = ShopifyClient.from_env()
    product_store = JSONProductStore(args.product_map)

    mapped_eans = set(product_store.list_eans())
    if not mapped_eans:
        print("No product mappings found in product_map.json")
        return

    allowed_eans: Optional[Set[str]] = None
    if args.ean_file:
        ean_file_path = Path(args.ean_file)
        if not ean_file_path.exists():
            raise FileNotFoundError(f"EAN allowlist file not found: {ean_file_path}")
        allowed_eans = load_ean_allowlist(str(ean_file_path))
        logging.info("Loaded %s allowed EANs from %s", len(allowed_eans), ean_file_path)

    allowed_brands: Optional[Set[str]] = None
    if args.brand_file:
        brand_file_path = Path(args.brand_file)
        if not brand_file_path.exists():
            raise FileNotFoundError(f"Brand allowlist file not found: {brand_file_path}")
        allowed_brands = load_brand_allowlist(str(brand_file_path))
        logging.info("Loaded %s allowed brands from %s", len(allowed_brands), brand_file_path)

    eans = select_subset_eans(
        snapshot=snapshot,
        mapped_eans=mapped_eans,
        limit=args.limit,
        require_ean=not args.allow_no_ean,
        brand_filter=args.brand.strip() or None,
        min_stock=args.min_stock,
        allowed_eans=allowed_eans,
        allowed_brands=allowed_brands,
    )

    logging.info("Preparing inventory sync for %s mapped products", len(eans))
    logging.info(
        "Filters: brand=%s min_stock=%s require_ean=%s ean_file=%s brand_file=%s",
        args.brand.strip() or "(none)",
        args.min_stock,
        not args.allow_no_ean,
        args.ean_file or "(none)",
        args.brand_file or "(none)",
    )

    for idx, ean in enumerate(eans, start=1):
        mapping = product_store.get_product_link(ean)
        if not mapping:
            continue

        snapshot_product = snapshot_by_ean.get(ean)
        if not snapshot_product:
            print("\n--------------------------------------------------")
            print(f"[{idx}/{len(eans)}] EAN: {ean}")
            print("SKIP: EAN not found in snapshot")
            continue

        title = clean_text(snapshot_product.get("name"), fallback="Unnamed BTS product")
        available = parse_stock(snapshot_product)

        print("\n--------------------------------------------------")
        print(f"[{idx}/{len(eans)}] {title}")
        print(f"EAN: {ean}")
        print(f"Shopify inventory_item_id: {mapping.shopify_inventory_item_id}")
        print(f"Target location_id: {location_id}")
        print(f"Target available stock: {available}")

        if not args.commit:
            print("DRY RUN: inventory not updated. Use --commit to apply changes.")
            continue

        resp = client.set_inventory_level(
            inventory_item_id=mapping.shopify_inventory_item_id,
            location_id=location_id,
            available=available,
        )

        inventory_level = resp.get("inventory_level", {}) if isinstance(resp, dict) else {}
        print(
            "UPDATED:",
            json.dumps(
                {
                    "inventory_item_id": inventory_level.get("inventory_item_id"),
                    "location_id": inventory_level.get("location_id"),
                    "available": inventory_level.get("available"),
                },
                ensure_ascii=False,
            ),
        )

    print("\nDone.")


if __name__ == "__main__":
    main()