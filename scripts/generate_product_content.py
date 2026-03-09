import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set

from catalog.filters import select_subset
from catalog.io import load_ean_allowlist, load_snapshot
from catalog.normalize import clean_product_title
from catalog.product_data import clean_text
from shopify.store import JSONProductStore


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_sizes(text: str) -> str:
    return re.sub(r"(\d+)\s*ml\b", r"\1 ml", text, flags=re.IGNORECASE)


def is_gift_set(title: str) -> bool:
    title_lower = title.lower()
    return (
        "set" in title_lower
        or "pieces" in title_lower
        or "gavesæt" in title_lower
        or "body" in title_lower
        or "gel" in title_lower
        or "lotion" in title_lower
        or "milk" in title_lower
        or "shower" in title_lower
        or "bath" in title_lower
    )


def is_homme(title: str) -> bool:
    return "homme" in title.lower()


def detect_product_type(title: str) -> str:
    lower = title.lower()
    if "eau de parfum" in lower:
        return "eau_de_parfum"
    if "eau de toilette" in lower:
        return "eau_de_toilette"
    return "duft"


def pretty_product_type(product_type: str) -> str:
    mapping = {
        "eau_de_parfum": "eau de parfum",
        "eau_de_toilette": "eau de toilette",
        "duft": "duft",
    }
    return mapping.get(product_type, "duft")


def extract_all_sizes(title: str) -> List[str]:
    matches = re.findall(r"(\d+\s*ml)", title, flags=re.IGNORECASE)
    cleaned = [normalize_sizes(x) for x in matches]
    seen = set()
    result: List[str] = []

    for item in cleaned:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def extract_primary_size(title: str) -> str:
    sizes = extract_all_sizes(title)
    return sizes[0] if sizes else ""


def remove_size_tokens(text: str) -> str:
    text = re.sub(r"\b\d+\s*ml\b", "", text, flags=re.IGNORECASE)
    return normalize_spaces(text)


def clean_set_title_base(title: str) -> str:
    text = title

    text = re.sub(r"^Set\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSet\s+\d+\s+Pieces\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s*Pieces\b", "", text, flags=re.IGNORECASE)

    text = re.sub(r"\bBody\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGel\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLotion\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMilk\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bShower\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBath\b", "", text, flags=re.IGNORECASE)

    text = remove_size_tokens(text)
    text = normalize_spaces(text)

    return text


def detect_set_components(text: str) -> List[str]:
    lower = text.lower()
    components: List[str] = []

    if "body" in lower and ("lotion" in lower or "milk" in lower):
        components.append("body lotion")
    elif "body" in lower:
        components.append("bodypleje")

    if "shower" in lower and "gel" in lower:
        components.append("shower gel")
    elif "gel" in lower:
        components.append("gel")

    return list(dict.fromkeys(components))


def build_title_da(product: Dict[str, Any]) -> str:
    source_title = clean_text(product.get("name"), fallback="Ukendt produkt")
    title = clean_product_title(source_title)

    if is_gift_set(title):
        base = clean_set_title_base(title)
        base = re.sub(r"\bEau de Parfum\s*$", "", base, flags=re.IGNORECASE)
        base = re.sub(r"\bEau de Toilette\s*$", "", base, flags=re.IGNORECASE)
        base = normalize_spaces(base)
        return f"{base} gavesæt"

    return normalize_spaces(title)


def choose_template_variant(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 3


def build_description_da(
    title_da: str,
    brand: str,
    product_type: str,
    size: str,
    source_title: str,
) -> str:
    type_text = pretty_product_type(product_type)
    brand_title = brand.title() if brand else "Produktet"
    variant = choose_template_variant(title_da)

    if is_gift_set(title_da):
        components = detect_set_components(source_title)

        if components:
            comp_text = " samt ".join(components)
            return (
                f"{title_da} fra {brand_title} er et gavesæt med duft og {comp_text}. "
                f"Et godt valg som gave eller til dig, der ønsker flere produkter fra samme serie."
            )

        return (
            f"{title_da} fra {brand_title} er et gavesæt med duft og tilhørende plejeprodukter. "
            f"Et godt valg som gave eller til dig, der ønsker flere produkter fra samme serie."
        )

    if is_homme(title_da):
        if variant == 0:
            return (
                f"{title_da} fra {brand_title} er en herreduft i {size}. "
                f"Et godt valg til dig, der ønsker en klassisk og anvendelig duft til hverdagsbrug og særlige anledninger."
            )
        if variant == 1:
            return (
                f"{title_da} fra {brand_title} er en herreduft i {size}. "
                f"Størrelsen gør den velegnet både som fast del af hverdagen og som gaveidé."
            )
        return (
            f"{title_da} fra {brand_title} er en herreduft i {size}. "
            f"En praktisk størrelse til dig, der ønsker en duft med et klassisk udtryk."
        )

    if variant == 0:
        return (
            f"{title_da} fra {brand_title} er en {type_text} i {size}. "
            f"Den praktiske størrelse gør den velegnet både til daglig brug og til at have med på farten."
        )
    if variant == 1:
        return (
            f"{title_da} fra {brand_title} er en {type_text} i {size}. "
            f"Et oplagt valg til dig, der ønsker en duft i en størrelse, der er nem at have med."
        )

    return (
        f"{title_da} fra {brand_title} fås her i {size}. "
        f"En praktisk størrelse, der passer godt til både hverdagsbrug og som gaveidé."
    )


def build_bullets_da(
    title_da: str,
    brand: str,
    product_type: str,
    size: str,
    source_title: str,
) -> List[str]:
    bullets: List[str] = []

    if is_gift_set(title_da):
        bullets.append("Gavesæt")

        if product_type in ("eau_de_parfum", "eau_de_toilette") and size:
            bullets.append(f"{pretty_product_type(product_type).capitalize()} {size}")
        elif size:
            bullets.append(size)

        components = detect_set_components(source_title)
        if components:
            if "body lotion" in components and "gel" in components:
                bullets.append("Indeholder også body lotion og gel")
            elif "body lotion" in components:
                bullets.append("Indeholder også body lotion")
            elif "gel" in components:
                bullets.append("Indeholder også gel")
            else:
                bullets.append("Indeholder flere produkter")
        else:
            bullets.append(f"Fra {brand.title()}")

        return bullets[:3]

    bullets.append(pretty_product_type(product_type).capitalize())

    if size:
        bullets.append(size)

    if is_homme(title_da):
        bullets.append("Herreduft")
    else:
        bullets.append(f"Fra {brand.title()}")

    return bullets[:3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="Path to BTS snapshot JSON")
    parser.add_argument("--product-map", default="data/product_map.json")
    parser.add_argument("--out", default="data/content_review.json")
    parser.add_argument("--brand", type=str, default="")
    parser.add_argument("--ean-file", type=str, default="")
    parser.add_argument("--limit", type=int, default=0, help="Number of products to generate content for (0 = no limit)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    snapshot = load_snapshot(args.snapshot)
    product_store = JSONProductStore(args.product_map)

    allowed_eans: Optional[Set[str]] = None
    if args.ean_file:
        allowed_eans = load_ean_allowlist(args.ean_file)

    subset = select_subset(
        products=snapshot,
        limit=args.limit,
        require_image=False,
        require_ean=True,
        brand_filter=args.brand.strip() or None,
        min_stock=0,
        allowed_eans=allowed_eans,
        allowed_brands=None,
    )

    output: Dict[str, Any] = {"products": []}

    for product in subset:
        ean = clean_text(product.get("ean"))
        brand = clean_text(product.get("manufacturer"))
        source_title = clean_text(product.get("name"))

        title_da = build_title_da(product)
        product_type = detect_product_type(title_da)
        size = "" if is_gift_set(title_da) else extract_primary_size(title_da)

        mapping = product_store.get_product_link(ean)
        shopify_product_id = mapping.shopify_product_id if mapping else None

        row = {
            "ean": ean,
            "shopify_product_id": shopify_product_id,
            "source_title": source_title,
            "brand": brand,
            "size": size,
            "generated": {
                "title_da": title_da,
                "description_da": build_description_da(title_da, brand, product_type, size, source_title),
                "bullets_da": build_bullets_da(title_da, brand, product_type, size, source_title),
            },
            "review": {
                "status": "pending",
                "notes": "",
            },
        }

        output["products"].append(row)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(output['products'])} products to {args.out}")


if __name__ == "__main__":
    main()