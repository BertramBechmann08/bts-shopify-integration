from typing import Any, Dict, List, Optional, Set

from catalog.product_data import clean_text, parse_stock


def product_matches_filters(
    product: Dict[str, Any],
    require_image: bool = True,
    require_ean: bool = True,
    brand_filter: Optional[str] = None,
    min_stock: int = 0,
    allowed_eans: Optional[Set[str]] = None,
    allowed_brands: Optional[Set[str]] = None,
) -> bool:
    ean = clean_text(product.get("ean"))
    name = clean_text(product.get("name"))
    manufacturer = clean_text(product.get("manufacturer"))
    image = clean_text(product.get("image"))
    stock = parse_stock(product)

    if require_ean and not ean:
        return False
    if require_image and not image:
        return False
    if not name:
        return False
    if stock < min_stock:
        return False

    if brand_filter and manufacturer.upper() != brand_filter.upper():
        return False

    if allowed_brands is not None and manufacturer.upper() not in allowed_brands:
        return False

    if allowed_eans is not None and ean not in allowed_eans:
        return False

    return True


def select_subset(
    products: List[Dict[str, Any]],
    limit: int,
    require_image: bool = True,
    require_ean: bool = True,
    brand_filter: Optional[str] = None,
    min_stock: int = 0,
    allowed_eans: Optional[Set[str]] = None,
    allowed_brands: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []

    for product in products:
        if not product_matches_filters(
            product=product,
            require_image=require_image,
            require_ean=require_ean,
            brand_filter=brand_filter,
            min_stock=min_stock,
            allowed_eans=allowed_eans,
            allowed_brands=allowed_brands,
        ):
            continue

        selected.append(product)
        if limit > 0 and len(selected) >= limit:
            break

    return selected