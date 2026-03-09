import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
import logging
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv

from catalog.filters import select_subset
from catalog.io import load_brand_allowlist, load_ean_allowlist, load_snapshot
from catalog.normalize import clean_product_title
from catalog.pricing import choose_price
from catalog.product_data import clean_text, parse_stock
from shopify.client import ShopifyClient
from shopify.store import JSONProductStore

load_dotenv()


def build_tags(product: Dict[str, Any]) -> str:
    tags = ["bts-sync"]

    manufacturer = clean_text(product.get("manufacturer"))
    if manufacturer:
        tags.append(f"brand:{manufacturer}")

    categories = clean_text(product.get("categories"))
    if categories:
        tags.append(f"bts_categories:{categories}")

    return ", ".join(tags)


def build_create_payload(product: Dict[str, Any]) -> Dict[str, Any]:
    raw_title = clean_text(product.get("name"), fallback="Unnamed BTS product")
    title = clean_product_title(raw_title)
    vendor = clean_text(product.get("manufacturer"), fallback="BTSWholesaler")
    barcode = clean_text(product.get("ean"))
    image_src = clean_text(product.get("image"))

    variant = {
        "price": choose_price(product),
        "sku": barcode or None,
        "barcode": barcode or None,
        "inventory_management": "shopify",
        "inventory_policy": "deny",
        "requires_shipping": True,
        "taxable": True,
    }

    payload: Dict[str, Any] = {
        "title": title,
        "body_html": "",
        "vendor": vendor,
        "product_type": vendor,
        "status": "draft",
        "tags": build_tags(product),
        "variants": [variant],
    }

    if image_src:
        payload["images"] = [{"src": image_src}]

    return payload


def build_update_payload(product: Dict[str, Any]) -> Dict[str, Any]:
    raw_title = clean_text(product.get("name"), fallback="Unnamed BTS product")
    title = clean_product_title(raw_title)
    vendor = clean_text(product.get("manufacturer"), fallback="BTSWholesaler")

    payload: Dict[str, Any] = {
        "title": title,
        "body_html": "",
        "vendor": vendor,
        "product_type": vendor,
        "status": "draft",
        "tags": build_tags(product),
    }

    return payload


def build_variant_update_payload(product: Dict[str, Any]) -> Dict[str, Any]:
    barcode = clean_text(product.get("ean"))

    return {
        "price": choose_price(product),
        "sku": barcode or None,
        "barcode": barcode or None,
        "inventory_management": "shopify",
        "inventory_policy": "deny",
        "requires_shipping": True,
        "taxable": True,
    }


def get_ids_from_created_product(created_product: Dict[str, Any]) -> Dict[str, int]:
    variants = created_product.get("variants", [])
    if not variants:
        raise RuntimeError("Created Shopify product has no variants")

    first_variant = variants[0]
    inventory_item_id = first_variant.get("inventory_item_id")
    variant_id = first_variant.get("id")
    product_id = created_product.get("id")

    if not product_id or not variant_id or not inventory_item_id:
        raise RuntimeError("Could not extract Shopify product/variant/inventory IDs")

    return {
        "product_id": int(product_id),
        "variant_id": int(variant_id),
        "inventory_item_id": int(inventory_item_id),
    }


def find_existing_match(
    client: ShopifyClient,
    product_store: JSONProductStore,
    product: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    ean = clean_text(product.get("ean"))
    if not ean:
        return None

    mapped = product_store.get_product_link(ean)
    if mapped:
        try:
            existing = client.get_product(mapped.shopify_product_id)
            existing_product = existing.get("product")
            if existing_product:
                return {
                    "source": "mapping",
                    "product": existing_product,
                    "variant": None,
                    "mapping": mapped,
                }
        except Exception:
            logging.warning("Mapped Shopify product for EAN=%s no longer exists; falling back to lookup", ean)

    found = client.get_variant_by_barcode_or_sku(ean)
    if found:
        return {
            "source": "shopify_lookup",
            "product": found["product"],
            "variant": found["variant"],
            "mapping": None,
        }

    return None


def save_mapping_from_product(
    product_store: JSONProductStore,
    ean: str,
    created_or_existing_product: Dict[str, Any],
) -> None:
    ids = get_ids_from_created_product(created_or_existing_product)
    product_store.put_product_link(
        ean=ean,
        shopify_product_id=ids["product_id"],
        shopify_variant_id=ids["variant_id"],
        shopify_inventory_item_id=ids["inventory_item_id"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="Path to BTS snapshot JSON")
    parser.add_argument("--limit", type=int, default=0, help="Number of products to sync (0 = no limit)")
    parser.add_argument("--commit", action="store_true", help="Actually create/update products in Shopify")
    parser.add_argument("--product-map", default="data/product_map.json", help="Path to local product mapping JSON")

    parser.add_argument("--brand", type=str, default="", help="Only sync products from this manufacturer/brand")
    parser.add_argument("--min-stock", type=int, default=0, help="Only sync products with stock >= this value")
    parser.add_argument("--ean-file", type=str, default="", help="Optional file containing one allowed EAN per line")
    parser.add_argument("--allow-no-image", action="store_true", help="Allow products without images")
    parser.add_argument("--allow-no-ean", action="store_true", help="Allow products without EAN")
    parser.add_argument("--brand-file", type=str, default="", help="Optional file containing one allowed brand per line")
    parser.add_argument("--mapped-only", action="store_true", help="Only sync products already present in product_map.json")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")

    products = load_snapshot(str(snapshot_path))
    client = ShopifyClient.from_env()
    product_store = JSONProductStore(args.product_map)

    mapped_eans: Optional[Set[str]] = None
    if args.mapped_only:
        mapped_eans = set(product_store.list_eans())

    allowed_eans: Optional[Set[str]] = None

    if args.ean_file:
        allowed_eans = load_ean_allowlist(args.ean_file)

    if mapped_eans is not None:
        if allowed_eans is None:
            allowed_eans = mapped_eans
        else:
            allowed_eans = allowed_eans.intersection(mapped_eans)

    allowed_brands: Optional[Set[str]] = None
    if args.brand_file:
        brand_file_path = Path(args.brand_file)
        if not brand_file_path.exists():
            raise FileNotFoundError(f"Brand allowlist file not found: {brand_file_path}")
        allowed_brands = load_brand_allowlist(str(brand_file_path))
        logging.info("Loaded %s allowed brands from %s", len(allowed_brands), brand_file_path)

    subset = select_subset(
        products=products,
        limit=args.limit,
        require_image=not args.allow_no_image,
        require_ean=not args.allow_no_ean,
        brand_filter=args.brand.strip() or None,
        min_stock=args.min_stock,
        allowed_eans=allowed_eans,
        allowed_brands=allowed_brands,
    )

    logging.info("Selected %s products from snapshot", len(subset))
    logging.info(
        "Filters: brand=%s min_stock=%s require_image=%s require_ean=%s ean_file=%s brand_file=%s",
        args.brand.strip() or "(none)",
        args.min_stock,
        not args.allow_no_image,
        not args.allow_no_ean,
        args.ean_file or "(none)",
        args.brand_file or "(none)",
    )

    for index, product in enumerate(subset, start=1):
        raw_title = clean_text(product.get("name"), fallback="Unnamed BTS product")
        title = clean_product_title(raw_title)
        ean = clean_text(product.get("ean"))
        price = choose_price(product)
        stock = parse_stock(product)
        manufacturer = clean_text(product.get("manufacturer"))

        print("\n--------------------------------------------------")
        print(f"[{index}/{len(subset)}] {title}")
        print(f"EAN: {ean or '(none)'}")
        print(f"Brand: {manufacturer or '(none)'}")
        print(f"Price (DKK): {price}")
        print(f"Stock: {stock}")

        existing = find_existing_match(client, product_store, product)

        if existing:
            existing_product = existing["product"]
            variant = None
            variants = existing_product.get("variants", [])
            if variants:
                variant = variants[0]

            print(
                f"MATCH FOUND: Shopify product id={existing_product.get('id')} "
                f"(source={existing['source']})"
            )

            update_payload = build_update_payload(product)
            variant_update_payload = build_variant_update_payload(product)

            print("Prepared Shopify update payload summary:")
            print(json.dumps(
                {
                    "id": existing_product.get("id"),
                    "title": update_payload["title"],
                    "vendor": update_payload["vendor"],
                    "status": update_payload["status"],
                    "tags": update_payload["tags"],
                    "variant_update": variant_update_payload,
                },
                indent=2,
                ensure_ascii=False,
            ))

            if not args.commit:
                print("DRY RUN: product not updated. Use --commit to update it in Shopify.")
                continue

            updated = client.update_product(int(existing_product["id"]), update_payload)
            updated_product = updated.get("product", {})

            if variant:
                client.update_variant(int(variant["id"]), variant_update_payload)

            refreshed = client.get_product(int(existing_product["id"]))
            refreshed_product = refreshed.get("product", updated_product)
            save_mapping_from_product(product_store, ean, refreshed_product)

            print(f"UPDATED: Shopify product id={refreshed_product.get('id')} title={refreshed_product.get('title')}")
            continue

        create_payload = build_create_payload(product)

        print("Prepared Shopify create payload summary:")
        print(json.dumps(
            {
                "title": create_payload["title"],
                "vendor": create_payload["vendor"],
                "status": create_payload["status"],
                "tags": create_payload["tags"],
                "variant": create_payload["variants"][0],
                "image_count": len(create_payload.get("images", [])),
            },
            indent=2,
            ensure_ascii=False,
        ))

        if not args.commit:
            print("DRY RUN: product not created. Use --commit to create it in Shopify.")
            continue

        created = client.create_product(create_payload)
        created_product = created.get("product", {})
        save_mapping_from_product(product_store, ean, created_product)
        print(f"CREATED: Shopify product id={created_product.get('id')} title={created_product.get('title')}")

    print("\nDone.")


if __name__ == "__main__":
    main()