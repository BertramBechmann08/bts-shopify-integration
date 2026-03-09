import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import json
from typing import Any, Dict, List

from dotenv import load_dotenv

from shopify.client import ShopifyClient

load_dotenv()


def load_review_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Review file must contain a JSON object")

    return data


def build_body_html(description_da: str, bullets_da: List[str]) -> str:
    lines = [f"<p>{description_da}</p>"]

    if bullets_da:
        lines.append("<ul>")
        for bullet in bullets_da:
            lines.append(f"<li>{bullet}</li>")
        lines.append("</ul>")

    return "".join(lines)


def get_approved_payload(row: Dict[str, Any]) -> Dict[str, Any] | None:
    review = row.get("review", {})
    generated = row.get("ai_rewrite") or row.get("generated", {})

    if not isinstance(review, dict) or review.get("status") != "approved":
        return None

    if not isinstance(generated, dict):
        return None

    title_da = str(generated.get("title_da") or "").strip()
    description_da = str(generated.get("description_da") or "").strip()
    bullets_raw = generated.get("bullets_da") or []

    if not title_da or not description_da:
        return None

    bullets_da: List[str] = []
    if isinstance(bullets_raw, list):
        for bullet in bullets_raw:
            text = str(bullet).strip()
            if text:
                bullets_da.append(text)

    return {
        "title": title_da,
        "body_html": build_body_html(description_da, bullets_da),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-file", default="data/content_review.json")
    parser.add_argument("--commit", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    client = ShopifyClient.from_env()
    doc = load_review_file(args.review_file)
    products = doc.get("products", [])

    if not isinstance(products, list):
        raise ValueError("Review file must contain a 'products' list")

    for row in products:
        if not isinstance(row, dict):
            continue

        shopify_product_id = row.get("shopify_product_id")
        ean = row.get("ean")

        payload = get_approved_payload(row)
        if payload is None:
            continue

        if not shopify_product_id:
            print(f"SKIP: missing shopify_product_id for EAN {ean}")
            continue

        print("\n----------------------------------------")
        print(f"Shopify product id: {shopify_product_id}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

        if not args.commit:
            print("DRY RUN: content not applied. Use --commit to update Shopify.")
            continue

        client.update_product(int(shopify_product_id), payload)
        print("UPDATED")

    print("\nDone.")


if __name__ == "__main__":
    main()