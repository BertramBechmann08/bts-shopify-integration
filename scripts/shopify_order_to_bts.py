import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from bts.client import BTSClient
from bts.store import JSONOrderStore
from shopify.client import ShopifyClient

load_dotenv()


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def pick_shopify_order(client: ShopifyClient, order_id: Optional[int], limit: int = 10) -> Dict[str, Any]:
    if order_id is not None:
        resp = client.get_order(order_id)
        order = resp.get("order")
        if not isinstance(order, dict):
            raise RuntimeError(f"Could not load Shopify order {order_id}")
        return order

    resp = client.list_orders(limit=limit, status="any")
    orders = resp.get("orders", []) if isinstance(resp, dict) else []
    if not orders:
        raise RuntimeError(
            "No Shopify orders found. Create a test order in Shopify admin using one of the BTS-synced products, then run this script again."
        )

    first_order = orders[0]
    if not isinstance(first_order, dict):
        raise RuntimeError("Unexpected Shopify order structure")
    return first_order


def extract_shopify_order_items(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    line_items = order.get("line_items", [])
    if not isinstance(line_items, list) or not line_items:
        raise ValueError("Shopify order has no line items")

    items: List[Dict[str, Any]] = []

    for idx, line in enumerate(line_items):
        if not isinstance(line, dict):
            continue

        sku = clean_text(line.get("sku"))
        barcode = clean_text(line.get("barcode"))
        quantity_raw = line.get("quantity")

        # Prefer SKU first. In your current sync SKU == EAN, which is what BTS needs.
        product_sku = sku or barcode

        if not product_sku:
            raise ValueError(
                f"Line item at index {idx} has neither SKU nor barcode; cannot map to BTS product"
            )

        if quantity_raw is None:
            raise ValueError(f"Missing quantity for line item at index {idx}")

        try:
            quantity_int = int(quantity_raw)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid quantity for line item at index {idx}: {quantity_raw!r}")

        if quantity_int <= 0:
            raise ValueError(f"Quantity must be > 0 for line item at index {idx}")

        items.append(
            {
                "sku": product_sku,
                "quantity": quantity_int,
                "title": clean_text(line.get("title")),
            }
        )

    return items


def extract_shopify_customer(order: Dict[str, Any]) -> Dict[str, Optional[str]]:
    shipping_raw = order.get("shipping_address") or order.get("billing_address")
    if not isinstance(shipping_raw, dict):
        raise ValueError("Shopify order does not contain a usable shipping or billing address")

    shipping: Dict[str, Any] = shipping_raw

    first_name = clean_text(shipping.get("first_name"))
    last_name = clean_text(shipping.get("last_name"))
    name = clean_text(
        f"{first_name} {last_name}".strip(),
        fallback=clean_text(shipping.get("name"), "Shopify Customer"),
    )

    address1 = clean_text(shipping.get("address1"))
    address2 = clean_text(shipping.get("address2"))
    full_address = address1 if not address2 else f"{address1}, {address2}"

    postal_code = clean_text(shipping.get("zip"))
    city = clean_text(shipping.get("city"))
    country_code = clean_text(shipping.get("country_code")).upper()
    phone = clean_text(shipping.get("phone"))

    if not name:
        raise ValueError("Missing customer name in Shopify order")
    if not full_address:
        raise ValueError("Missing address in Shopify order")
    if not postal_code:
        raise ValueError("Missing postal code in Shopify order")
    if not city:
        raise ValueError("Missing city in Shopify order")
    if not country_code:
        raise ValueError("Missing country_code in Shopify order")

    if not phone:
        phone = "+4500000000"

    state_code_raw = clean_text(shipping.get("province_code")).upper()
    state_code: Optional[str] = state_code_raw if state_code_raw else None

    return {
        "client_name": name,
        "address": full_address,
        "postal_code": postal_code,
        "city": city,
        "country_code": country_code,
        "telephone": phone,
        "state_code": state_code,
    }


def build_shipping_params(country_code: str, postal_code: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "address[country_code]": country_code,
        "address[postal_code]": postal_code,
    }
    for i, it in enumerate(items):
        params[f"products[{i}][sku]"] = it["sku"]
        params[f"products[{i}][quantity]"] = str(it["quantity"])
    return params


def pick_shipping_cost_id(shipping_resp: Any) -> int:
    if isinstance(shipping_resp, list):
        options = shipping_resp
    elif isinstance(shipping_resp, dict):
        options = None
        for key in ("shipping_costs", "shipping_prices", "shipping_methods", "data"):
            val = shipping_resp.get(key)
            if isinstance(val, list) and val:
                options = val
                break
        if options is None:
            raise ValueError(f"No shipping options list found. Keys: {list(shipping_resp.keys())}")
    else:
        raise TypeError(f"Unexpected shipping_resp type: {type(shipping_resp)}")

    if not options:
        raise ValueError("No shipping options returned")

    def cost_num(opt: dict) -> float:
        raw = opt.get("shipping_cost") or "0"
        try:
            return float(str(raw).replace("€", "").replace(",", ".").strip())
        except Exception:
            return 0.0

    def delivery_num(opt: dict) -> int:
        raw = opt.get("delivery_time") or "999"
        try:
            return int(str(raw).strip())
        except Exception:
            return 999

    chosen = sorted(options, key=lambda o: (cost_num(o), delivery_num(o)))[0]
    return int(chosen["id"])


def build_create_order_payload(
    *,
    payment_method: str,
    shipping_cost_id: int,
    client_name: str,
    address: str,
    postal_code: str,
    city: str,
    country_code: str,
    telephone: str,
    items: List[Dict[str, Any]],
    dropshipping: int = 1,
    state_code: Optional[str] = None,
) -> Dict[str, str]:
    payload: Dict[str, str] = {
        "payment_method": payment_method,
        "shipping_cost_id": str(shipping_cost_id),
        "client_name": client_name,
        "address": address,
        "postal_code": postal_code,
        "city": city,
        "country_code": country_code,
        "telephone": telephone,
        "dropshipping": str(dropshipping),
    }

    if state_code:
        payload["state_code"] = state_code

    for i, it in enumerate(items):
        payload[f"products[{i}][sku]"] = str(it["sku"])
        payload[f"products[{i}][quantity]"] = str(it["quantity"])

    return payload


def validate_country_supported(client: BTSClient, country_code: str) -> None:
    resp = client.get_countries()
    supported_codes = set()

    def add_code(value: str) -> None:
        code = str(value).strip().upper()
        if len(code) == 2:
            supported_codes.add(code)

    def parse_node(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                parse_node(item)
        elif isinstance(node, dict):
            if node.get("country_code"):
                add_code(node["country_code"])
            for key, value in node.items():
                if isinstance(key, str) and len(key.strip()) == 2 and isinstance(value, (str, dict)):
                    add_code(key)
                if isinstance(value, (list, dict)):
                    parse_node(value)

    parse_node(resp)

    if not supported_codes:
        raise RuntimeError("Could not determine supported countries from BTS getCountries response")

    if country_code.upper() not in supported_codes:
        raise ValueError(f"Country {country_code} is not supported by BTS")

    logging.info("Country validation passed: %s is supported", country_code)


def validate_stock_available(client: BTSClient, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    skus = [item["sku"] for item in items]
    stock_resp = client.get_product_stock(skus)

    if not isinstance(stock_resp, dict):
        raise RuntimeError(f"Unexpected getProductStock response type: {type(stock_resp)}")

    products = stock_resp.get("products", {})
    if not isinstance(products, dict):
        raise RuntimeError("getProductStock response does not contain a 'products' dict")

    for item in items:
        sku = item["sku"]
        requested_qty = int(item["quantity"])
        row = products.get(sku)

        if not isinstance(row, dict):
            raise ValueError(f"SKU {sku} was not returned by BTS stock endpoint")

        availability = str(row.get("availability") or "").strip().lower()
        stock_value = row.get("stock", 0)

        try:
            available_qty = int(stock_value)
        except (TypeError, ValueError):
            available_qty = 0

        if availability == "not_found":
            raise ValueError(f"SKU {sku} was not found in BTS catalog")

        if available_qty < requested_qty:
            raise ValueError(
                f"Insufficient stock for SKU {sku}: requested={requested_qty}, available={available_qty}"
            )

        logging.info(
            "Stock validation passed for SKU=%s requested=%s available=%s",
            sku,
            requested_qty,
            available_qty,
        )

    return stock_resp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shopify-order-id", type=int, default=None, help="Specific Shopify order ID to process")
    parser.add_argument("--limit", type=int, default=10, help="How many Shopify orders to fetch when no ID is given")
    parser.add_argument("--commit", action="store_true", help="Actually create the BTS order")
    parser.add_argument("--store-path", type=str, default="data/order_map.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    shopify_client = ShopifyClient.from_env()
    bts_client = BTSClient.from_env()
    order_store = JSONOrderStore(args.store_path)

    order = pick_shopify_order(shopify_client, args.shopify_order_id, limit=args.limit)

    shopify_order_id_raw = order.get("id")
    if shopify_order_id_raw is None:
        raise RuntimeError("Shopify order has no id")

    shopify_order_id = str(shopify_order_id_raw)

    existing = order_store.get_order_link(shopify_order_id)
    if existing:
        logging.info(
            "Dedupe hit: Shopify order %s already mapped to BTS order %s",
            shopify_order_id,
            existing.bts_order_number,
        )
        bts_order = bts_client.get_order(existing.bts_order_number)
        print(json.dumps(bts_order, indent=2, ensure_ascii=False))
        return

    items = extract_shopify_order_items(order)
    customer = extract_shopify_customer(order)
    country_code = customer.get("country_code")
    postal_code = customer.get("postal_code")
    client_name = customer.get("client_name")
    address = customer.get("address")
    city = customer.get("city")
    telephone = customer.get("telephone")

    if not country_code:
        raise RuntimeError("Customer country_code is missing")
    if not postal_code:
        raise RuntimeError("Customer postal_code is missing")
    if not client_name:
        raise RuntimeError("Customer client_name is missing")
    if not address:
        raise RuntimeError("Customer address is missing")
    if not city:
        raise RuntimeError("Customer city is missing")
    if not telephone:
        raise RuntimeError("Customer telephone is missing")

    print("Shopify order summary:")
    print(json.dumps(
        {
            "shopify_order_id": shopify_order_id,
            "name": order.get("name"),
            "email": order.get("email"),
            "customer": customer,
            "items": items,
        },
        indent=2,
        ensure_ascii=False,
    ))

    validate_country_supported(bts_client, country_code)
    validate_stock_available(bts_client, items)

    shipping_params = build_shipping_params(
        country_code=country_code,
        postal_code=postal_code,
        items=items,
    )
    shipping_resp = bts_client.get_shipping_prices(shipping_params)

    print("\nBTS shipping response:")
    print(json.dumps(shipping_resp, indent=2, ensure_ascii=False))

    shipping_cost_id = pick_shipping_cost_id(shipping_resp)
    logging.info("Chosen shipping_cost_id=%s", shipping_cost_id)

    payload = build_create_order_payload(
        payment_method="banktransfer",
        shipping_cost_id=shipping_cost_id,
        client_name=client_name,
        address=address,
        postal_code=postal_code,
        city=city,
        country_code=country_code,
        telephone=telephone,
        state_code=customer.get("state_code"),
        items=items,
        dropshipping=1,
    )

    print("\n--- BTS setCreateOrder payload (x-www-form-urlencoded) ---")
    for k in sorted(payload.keys()):
        print(f"{k}={payload[k]}")
    print(f"\nexternal_id={shopify_order_id}")

    if not args.commit:
        print("\nDRY RUN: not creating BTS order. Use --commit to create a real BTS order.")
        return

    resp = bts_client.create_order(payload)

    print("\nBTS create order response:")
    print(json.dumps(resp, indent=2, ensure_ascii=False))

    if isinstance(resp, str):
        bts_order_number = resp.strip()
    elif isinstance(resp, int):
        bts_order_number = str(resp)
    elif isinstance(resp, dict):
        bts_order_number = (
            resp.get("order_number")
            or resp.get("order_id")
            or resp.get("data", {}).get("order_number")
            or resp.get("data", {}).get("order_id")
        )
        if bts_order_number is not None:
            bts_order_number = str(bts_order_number)
    else:
        bts_order_number = None

    if not bts_order_number:
        raise RuntimeError("Could not find BTS order number in response. Inspect the response above.")

    order_store.put_order_link(shopify_order_id, str(bts_order_number))
    logging.info("Stored mapping Shopify order %s -> BTS order %s", shopify_order_id, bts_order_number)


if __name__ == "__main__":
    main()