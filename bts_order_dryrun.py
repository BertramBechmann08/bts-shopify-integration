import argparse
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set

from bts_client import BTSClient
from bts_store import JSONStore


def load_test_order(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Order file must contain a JSON object")

    items = data.get("items")
    customer = data.get("customer")

    if not isinstance(items, list) or not items:
        raise ValueError("Order file must contain a non-empty 'items' list")
    if not isinstance(customer, dict):
        raise ValueError("Order file must contain a 'customer' object")

    required_customer_fields = [
        "client_name",
        "address",
        "postal_code",
        "city",
        "country_code",
        "telephone",
    ]
    missing_customer = [field for field in required_customer_fields if not customer.get(field)]
    if missing_customer:
        raise ValueError(f"Missing customer fields: {', '.join(missing_customer)}")

    normalized_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {idx} must be an object")

        sku = item.get("sku")
        quantity = item.get("quantity")

        if not sku:
            raise ValueError(f"Item at index {idx} is missing 'sku'")
        if quantity is None:
            raise ValueError(f"Item at index {idx} is missing 'quantity'")

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValueError(f"Item at index {idx} has invalid quantity: {quantity!r}")

        if quantity <= 0:
            raise ValueError(f"Item at index {idx} must have quantity > 0")

        normalized_items.append(
            {
                "sku": str(sku).strip(),
                "quantity": quantity,
            }
        )

    return {
        "items": normalized_items,
        "customer": {
            "client_name": str(customer["client_name"]).strip(),
            "address": str(customer["address"]).strip(),
            "postal_code": str(customer["postal_code"]).strip(),
            "city": str(customer["city"]).strip(),
            "country_code": str(customer["country_code"]).strip().upper(),
            "telephone": str(customer["telephone"]).strip(),
            "state_code": str(customer["state_code"]).strip().upper() if customer.get("state_code") else None,
        },
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
            return float(str(raw).replace("€", "").strip())
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


def stable_external_id(customer: Dict[str, str], items: List[Dict[str, Any]]) -> str:
    sig = {
        "name": customer.get("client_name", ""),
        "postal_code": customer.get("postal_code", ""),
        "country_code": customer.get("country_code", ""),
        "items": [{"sku": it["sku"], "quantity": int(it["quantity"])} for it in items],
    }
    raw = json.dumps(sig, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "proto_" + hashlib.sha256(raw).hexdigest()[:16]


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
        print("Countries response:")
        print(json.dumps(resp, indent=2, ensure_ascii=False))
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

    print("Stock validation response:")
    print(json.dumps(stock_resp, indent=2, ensure_ascii=False))

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
    parser.add_argument(
        "--order-file",
        type=str,
        default="data/test_order.json",
        help="Path to JSON file containing items + customer data.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually create a BTS order using payment_method=banktransfer.",
    )
    parser.add_argument(
        "--external-id",
        type=str,
        default="",
        help="Idempotency key. Later this should be the Shopify order id.",
    )
    parser.add_argument("--store-path", type=str, default="data/order_map.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    client = BTSClient.from_env()
    store = JSONStore(args.store_path)

    order_data = load_test_order(args.order_file)
    items = order_data["items"]
    customer = order_data["customer"]

    external_id = args.external_id.strip() or stable_external_id(customer, items)

    existing = store.get_order_link(external_id)
    if existing:
        logging.info(
            "Dedupe hit: external_id=%s already mapped to BTS order %s",
            external_id,
            existing.bts_order_number,
        )
        order = client.get_order(existing.bts_order_number)
        print(json.dumps(order, indent=2, ensure_ascii=False))
        return

    country_code = customer["country_code"]
    postal_code = customer["postal_code"]

    validate_country_supported(client, country_code)
    validate_stock_available(client, items)

    shipping_params = build_shipping_params(country_code, postal_code, items)
    shipping_resp = client.get_shipping_prices(shipping_params)

    print("Shipping response:")
    print(json.dumps(shipping_resp, indent=2, ensure_ascii=False))

    shipping_cost_id = pick_shipping_cost_id(shipping_resp)
    logging.info("Chosen shipping_cost_id=%s", shipping_cost_id)

    payload = build_create_order_payload(
        payment_method="banktransfer",
        shipping_cost_id=shipping_cost_id,
        client_name=customer["client_name"],
        address=customer["address"],
        postal_code=customer["postal_code"],
        city=customer["city"],
        country_code=customer["country_code"],
        telephone=customer["telephone"],
        state_code=customer.get("state_code"),
        items=items,
        dropshipping=1,
    )

    print("\n--- setCreateOrder payload (x-www-form-urlencoded) ---")
    for k in sorted(payload.keys()):
        print(f"{k}={payload[k]}")
    print(f"\nexternal_id={external_id}")

    if not args.commit:
        print("\nDRY RUN: not creating order. Use --commit to create a real BTS order.")
        return

    resp = client.create_order(payload)

    print("\nCreate order response:")
    print(json.dumps(resp, indent=2, ensure_ascii=False))

    bts_order_number = (
        resp.get("order_number")
        or resp.get("order_id")
        or resp.get("data", {}).get("order_number")
        or resp.get("data", {}).get("order_id")
    )
    if not bts_order_number:
        raise RuntimeError("Could not find BTS order number in response. Inspect the response above.")

    store.put_order_link(external_id, str(bts_order_number))
    logging.info("Stored mapping external_id=%s -> bts_order_number=%s", external_id, bts_order_number)


if __name__ == "__main__":
    main()