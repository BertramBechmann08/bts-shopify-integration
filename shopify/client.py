import os
import time
from typing import Any, Dict, Optional

import requests


class ShopifyHTTPError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class ShopifyClient:
    def __init__(
        self,
        store: str,
        token: str,
        api_version: str = "2025-10",
        timeout_seconds: int = 30,
    ) -> None:
        self.store = store.strip()
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.base_url = f"https://{self.store}/admin/api/{self.api_version}"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Shopify-Access-Token": token,
                "Content-Type": "application/json",
            }
        )

    @staticmethod
    def from_env() -> "ShopifyClient":
        store = os.getenv("SHOPIFY_STORE", "").strip()
        token = os.getenv("SHOPIFY_ADMIN_TOKEN", "").strip()
        api_version = os.getenv("SHOPIFY_API_VERSION", "2025-10").strip()
        timeout = int(os.getenv("SHOPIFY_HTTP_TIMEOUT_SECONDS", "30"))

        if not store:
            raise RuntimeError("Missing SHOPIFY_STORE in environment")
        if not token:
            raise RuntimeError("Missing SHOPIFY_ADMIN_TOKEN in environment")

        return ShopifyClient(store=store, token=token, api_version=api_version, timeout_seconds=timeout)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"
    
    def _request_with_retry(self, method: Any, url: str, **kwargs: Any) -> requests.Response:
        last_response: Optional[requests.Response] = None

        for attempt in range(5):
            try:
                response = method(url, timeout=self.timeout_seconds, **kwargs)
            except requests.RequestException as e:
                if attempt == 4:
                    raise ShopifyHTTPError(f"Request {url} failed after retries: {e}") from e
                time.sleep(1.5 * (attempt + 1))
                continue

            last_response = response

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_seconds = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                except ValueError:
                    wait_seconds = 2.0 * (attempt + 1)

                time.sleep(wait_seconds)
                continue

            if 500 <= response.status_code < 600:
                if attempt == 4:
                    break
                time.sleep(1.5 * (attempt + 1))
                continue

            return response

        if last_response is None:
            raise ShopifyHTTPError(f"Request {url} failed without a response")

        return last_response

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        try:
            r = self._request_with_retry(self.session.get, url, params=params)
        except requests.RequestException as e:
            raise ShopifyHTTPError(f"GET {url} failed: {e}") from e

        if not r.ok:
            raise ShopifyHTTPError(f"GET {url} -> HTTP {r.status_code}", r.status_code, r.text[:2000])

        return r.json()

    def post(self, path: str, data: Dict[str, Any]) -> Any:
        url = self._url(path)
        try:
            r = self._request_with_retry(self.session.post, url, json=data)
        except requests.RequestException as e:
            raise ShopifyHTTPError(f"POST {url} failed: {e}") from e

        if not r.ok:
            raise ShopifyHTTPError(f"POST {url} -> HTTP {r.status_code}", r.status_code, r.text[:2000])

        return r.json()

    def put(self, path: str, data: Dict[str, Any]) -> Any:
        url = self._url(path)
        try:
            r = self._request_with_retry(self.session.put, url, json=data)
        except requests.RequestException as e:
            raise ShopifyHTTPError(f"PUT {url} failed: {e}") from e

        if not r.ok:
            raise ShopifyHTTPError(f"PUT {url} -> HTTP {r.status_code}", r.status_code, r.text[:2000])

        return r.json()

    # ---- Convenience methods ----

    def get_shop(self) -> Any:
        return self.get("shop.json")

    def list_products(self, limit: int = 10) -> Any:
        return self.get("products.json", params={"limit": limit})

    def create_product(self, product_payload: Dict[str, Any]) -> Any:
        return self.post("products.json", {"product": product_payload})

    def update_product(self, product_id: int, product_payload: Dict[str, Any]) -> Any:
        payload = {"product": {"id": product_id, **product_payload}}
        return self.put(f"products/{product_id}.json", payload)

    def get_product(self, product_id: int) -> Any:
        return self.get(f"products/{product_id}.json")

    def find_products_by_title(self, title: str, limit: int = 10) -> Any:
        return self.get("products.json", params={"title": title, "limit": limit})

    def get_variant_by_barcode_or_sku(self, value: str) -> Optional[Dict[str, Any]]:
        if not value:
            return None

        products_resp = self.get("products.json", params={"limit": 250})
        products = products_resp.get("products", []) if isinstance(products_resp, dict) else []

        for product in products:
            for variant in product.get("variants", []):
                if str(variant.get("barcode") or "").strip() == value:
                    return {"product": product, "variant": variant}
                if str(variant.get("sku") or "").strip() == value:
                    return {"product": product, "variant": variant}

        return None
    
    def set_inventory_level(self, inventory_item_id: int, location_id: int, available: int) -> Any:
        payload = {
            "location_id": int(location_id),
            "inventory_item_id": int(inventory_item_id),
            "available": int(available),
        }
        return self.post("inventory_levels/set.json", payload)

    def get_inventory_levels(self, inventory_item_ids: str, location_ids: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {"inventory_item_ids": inventory_item_ids}
        if location_ids:
            params["location_ids"] = location_ids
        return self.get("inventory_levels.json", params=params)

    def update_variant(self, variant_id: int, variant_payload: Dict[str, Any]) -> Any:
        payload = {"variant": {"id": variant_id, **variant_payload}}
        return self.put(f"variants/{variant_id}.json", payload)
    
    def get_order(self, order_id: int) -> Any:
        return self.get(f"orders/{order_id}.json")

    def list_orders(self, limit: int = 10, status: str = "any") -> Any:
        return self.get("orders.json", params={"limit": limit, "status": status})
    
    def get_fulfillment_orders(self, order_id: int) -> Any:
        return self.get(f"orders/{order_id}/fulfillment_orders.json")

    def create_fulfillment(
        self,
        fulfillment_order_id: int,
        tracking_number: str,
        tracking_company: str,
        notify_customer: bool = False,
    ) -> Any:
        payload = {
            "fulfillment": {
                "line_items_by_fulfillment_order": [
                    {
                        "fulfillment_order_id": int(fulfillment_order_id),
                    }
                ],
                "tracking_info": {
                    "number": tracking_number,
                    "company": tracking_company,
                },
                "notify_customer": notify_customer,
            }
        }
        return self.post("fulfillments.json", payload)