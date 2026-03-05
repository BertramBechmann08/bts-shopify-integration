import os
import json
import logging
from typing import Dict, Any, List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

HTTP_TIMEOUT_SECONDS = 60

SHIPPING_URL = "https://api.btswholesaler.com/v1/api/getShippingPrices"
CREATE_ORDER_URL = "https://api.btswholesaler.com/v1/api/setCreateOrder"
GET_ORDER_URL = "https://api.btswholesaler.com/v1/api/getOrder"
GET_COUNTRIES_URL = "https://api.btswholesaler.com/v1/api/getCountries"
GET_TRACKINGS_URL = "https://api.btswholesaler.com/v1/api/getTrackings"


def get_token() -> str:
    token = os.getenv("BTS_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing BTS_API_TOKEN env var. Put it in .env as BTS_API_TOKEN=...")
    return token


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def get_countries(session: requests.Session) -> Dict[str, Any]:
    r = session.get(GET_COUNTRIES_URL, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def get_shipping_prices(
    session: requests.Session,
    country_code: str,
    postal_code: str,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # Docs show nested params like: address[country_code], products[0][sku], etc.
    params: Dict[str, Any] = {
        "address[country_code]": country_code,
        "address[postal_code]": postal_code,
    }
    for i, it in enumerate(items):
        params[f"products[{i}][sku]"] = it["sku"]
        params[f"products[{i}][quantity]"] = str(it["quantity"])

    r = session.get(SHIPPING_URL, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def pick_shipping_cost_id(shipping_resp) -> int:
    if isinstance(shipping_resp, list):
        options = shipping_resp
    elif isinstance(shipping_resp, dict):
        for key in ("shipping_costs", "shipping_prices", "shipping_methods", "data"):
            val = shipping_resp.get(key)
            if isinstance(val, list) and val:
                options = val
                break
        else:
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
    state_code: str | None = None,
) -> Dict[str, str]:
    # setCreateOrder requires x-www-form-urlencoded -> requests.post(..., data=payload)
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


def create_order_real(session: requests.Session, payload: Dict[str, str]) -> Dict[str, Any]:
    # WARNING: This creates a real order. Only run when Henrik approves.
    r = session.post(
        CREATE_ORDER_URL,
        data=payload,  # not json=
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    return r.json()


def get_order(session: requests.Session, order_number: str) -> Dict[str, Any]:
    r = session.get(GET_ORDER_URL, params={"order_number": order_number}, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    session = make_session(get_token())

    # ---- TEST INPUT (safe, no order is created) ----
    # Use an EAN/SKU from your snapshot file
    items = [{"sku": "3760269849303", "quantity": 1}]

    # Destination (use real DK data later; verify DK is supported by getCountries)
    country_code = "DK"
    postal_code = "2100"

    # Customer details (dummy for now)
    customer = {
        "client_name": "Test Customer",
        "address": "Test Street 1",
        "postal_code": postal_code,
        "city": "Copenhagen",
        "country_code": country_code,
        "telephone": "+4512345678",
    }

    # 1) Validate supported countries (optional but useful)
    # countries = get_countries(session)
    # logging.info("Countries response keys: %s", list(countries.keys()))

    # 2) Get shipping prices -> choose shipping_cost_id
    shipping_resp = get_shipping_prices(session, country_code=country_code, postal_code=postal_code, items=items)
    print("Shipping response (first 800 chars):")
    print(json.dumps(shipping_resp, ensure_ascii=False)[:800])

    shipping_cost_id = pick_shipping_cost_id(shipping_resp)
    logging.info("Chosen shipping_cost_id=%s", shipping_cost_id)

    # 3) Build create-order payload (DRY RUN)
    payload = build_create_order_payload(
        payment_method="banktransfer",  # safe testing: stays Pending Payment
        shipping_cost_id=shipping_cost_id,
        items=items,
        dropshipping=1,
        **customer,
    )

    print("\n--- DRY RUN: setCreateOrder payload (x-www-form-urlencoded) ---")
    for k in sorted(payload.keys()):
        print(f"{k}={payload[k]}")

    print("\nNot creating order. When approved, call create_order_real(session, payload).")


if __name__ == "__main__":
    main()