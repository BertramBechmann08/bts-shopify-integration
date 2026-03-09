import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from bts.client import BTSClient
from bts.store import JSONStore
from shopify.client import ShopifyClient

load_dotenv()


def extract_tracking_map(resp: Any) -> Dict[str, Dict[str, Any]]:
    """
    Normalize BTS getTrackings response into:
    {bts_order_number: tracking_row_dict}
    """
    result: Dict[str, Dict[str, Any]] = {}

    if isinstance(resp, list):
        rows = resp
    elif isinstance(resp, dict):
        rows = None
        for key in ("trackings", "data", "orders"):
            value = resp.get(key)
            if isinstance(value, list):
                rows = value
                break
        if rows is None:
            rows = []
    else:
        rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        order_number = (
            row.get("order_number")
            or row.get("order_id")
            or row.get("reference")
        )
        if not order_number:
            continue

        result[str(order_number)] = row

    return result


def extract_tracking_fields(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    tracking_number = (
        row.get("tracking")
        or row.get("tracking_number")
        or row.get("tracking_code")
        or row.get("tracking_no")
    )
    tracking_company = (
        row.get("shipping_company")
        or row.get("company_name")
        or row.get("carrier")
        or row.get("tracking_company")
    )

    tracking_number_str = str(tracking_number).strip() if tracking_number else None
    tracking_company_str = str(tracking_company).strip() if tracking_company else None

    return tracking_number_str, tracking_company_str


def get_shopify_fulfillment_order_id(shopify_client: ShopifyClient, shopify_order_id: int) -> int:
    resp = shopify_client.get_fulfillment_orders(shopify_order_id)
    fulfillment_orders = resp.get("fulfillment_orders", []) if isinstance(resp, dict) else []

    if not fulfillment_orders:
        raise RuntimeError(f"No fulfillment orders found for Shopify order {shopify_order_id}")

    first = fulfillment_orders[0]
    fulfillment_order_id = first.get("id")
    if fulfillment_order_id is None:
        raise RuntimeError(f"Fulfillment order for Shopify order {shopify_order_id} has no id")

    return int(fulfillment_order_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-path", type=str, default="data/order_map.json")
    parser.add_argument("--commit", action="store_true", help="Actually create Shopify fulfillment with tracking")
    parser.add_argument("--notify-customer", action="store_true", help="Notify customer when creating fulfillment")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    bts_client = BTSClient.from_env()
    shopify_client = ShopifyClient.from_env()
    store = JSONStore(args.store_path)

    doc = store._load()
    orders = doc.get("orders", {})

    if not orders:
        print("No stored orders found.")
        return

    bts_order_numbers: List[str] = []
    reverse_map: Dict[str, str] = {}

    for shopify_order_id, row in orders.items():
        bts_order_number = row.get("bts_order_number")
        if not bts_order_number:
            continue
        bts_order_number_str = str(bts_order_number)
        bts_order_numbers.append(bts_order_number_str)
        reverse_map[bts_order_number_str] = str(shopify_order_id)

    if not bts_order_numbers:
        print("No BTS order numbers found.")
        return

    resp = bts_client.get_trackings(bts_order_numbers)
    tracking_map = extract_tracking_map(resp)

    print("BTS tracking response:")
    print(json.dumps(resp, indent=2, ensure_ascii=False))

    for bts_order_number in bts_order_numbers:
        shopify_order_id = reverse_map[bts_order_number]
        row = tracking_map.get(bts_order_number)

        print("\n--------------------------------------------------")
        print(f"Shopify order: {shopify_order_id}")
        print(f"BTS order: {bts_order_number}")

        if not row:
            print("No tracking row returned yet.")
            continue

        tracking_number, tracking_company = extract_tracking_fields(row)

        print(f"Tracking company: {tracking_company or '(none)'}")
        print(f"Tracking number: {tracking_number or '(none)'}")

        if not tracking_number:
            print("No tracking number available yet.")
            continue

        shopify_order_id_int = int(shopify_order_id)
        fulfillment_order_id = get_shopify_fulfillment_order_id(shopify_client, shopify_order_id_int)

        print(f"Shopify fulfillment_order_id: {fulfillment_order_id}")

        if not args.commit:
            print("DRY RUN: fulfillment not created. Use --commit to update Shopify.")
            continue

        fulfillment_resp = shopify_client.create_fulfillment(
            fulfillment_order_id=fulfillment_order_id,
            tracking_number=tracking_number,
            tracking_company=tracking_company or "GLS",
            notify_customer=args.notify_customer,
        )

        print("Shopify fulfillment response:")
        print(json.dumps(fulfillment_resp, indent=2, ensure_ascii=False))

    print("\nDone.")


if __name__ == "__main__":
    main()