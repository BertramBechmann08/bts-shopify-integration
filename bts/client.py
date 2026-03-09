import os
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import requests

ParamsType = Optional[Union[Dict[str, Any], Sequence[Tuple[str, str]]]]


class BTSHTTPError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class BTSClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.btswholesaler.com/v1/api",
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    @staticmethod
    def from_env() -> "BTSClient":
        token = os.getenv("BTS_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Missing BTS_API_TOKEN env var. Put it in .env as BTS_API_TOKEN=...")
        base_url = os.getenv("BTS_API_BASE_URL", "https://api.btswholesaler.com/v1/api").strip()
        timeout = int(os.getenv("BTS_HTTP_TIMEOUT_SECONDS", "60"))
        return BTSClient(token=token, base_url=base_url, timeout_seconds=timeout)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path: str, params: ParamsType = None) -> Any:
        url = self._url(path)
        try:
            r = self.session.get(url, params=params, timeout=self.timeout_seconds)
        except requests.RequestException as e:
            raise BTSHTTPError(f"GET {url} failed: {e}") from e

        if not r.ok:
            raise BTSHTTPError(f"GET {url} -> HTTP {r.status_code}", r.status_code, r.text[:2000])
        return r.json()

    def post_form(self, path: str, data: Dict[str, str]) -> Any:
        url = self._url(path)
        try:
            r = self.session.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            raise BTSHTTPError(f"POST {url} failed: {e}") from e

        if not r.ok:
            raise BTSHTTPError(f"POST {url} -> HTTP {r.status_code}", r.status_code, r.text[:2000])
        return r.json()

    def get_countries(self) -> Any:
        return self.get("getCountries")

    def get_feed_status(self) -> Any:
        return self.get("getFeedStatus")

    def get_product_changes(self, since: str, page: int = 1, page_size: int = 200) -> Any:
        return self.get(
            "getProductChanges",
            params={"since": since, "page": page, "page_size": page_size},
        )

    def get_product_stock(self, skus: List[str]) -> Any:
        params: List[Tuple[str, str]] = [("product_sku[]", sku) for sku in skus]
        return self.get("getProductStock", params=params)

    def get_shipping_prices(self, params: ParamsType) -> Any:
        return self.get("getShippingPrices", params=params)

    def create_order(self, payload: Dict[str, str]) -> Any:
        return self.post_form("setCreateOrder", data=payload)

    def get_order(self, order_number: str) -> Any:
        return self.get("getOrder", params={"order_number": order_number})

    def get_trackings(self, order_numbers: List[str]) -> Any:
        params: List[Tuple[str, str]] = [("order_number[]", order_no) for order_no in order_numbers]
        return self.get("getTrackings", params=params)