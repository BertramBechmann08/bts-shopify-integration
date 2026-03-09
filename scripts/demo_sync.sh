#!/usr/bin/env bash
set -euo pipefail

SNAPSHOT="${1:-data/bts_snapshot_full_20260309_165523.json}"
PRODUCT_MAP="${2:-data/product_map.json}"
REVIEW_FILE="${3:-data/content_review_existing.json}"

echo "== BTS -> Shopify demo run =="
echo "Snapshot:    $SNAPSHOT"
echo "Product map: $PRODUCT_MAP"
echo "Review file: $REVIEW_FILE"

if [[ ! -f "$SNAPSHOT" ]]; then
  echo "ERROR: snapshot file not found: $SNAPSHOT"
  exit 1
fi

if [[ ! -f "$PRODUCT_MAP" ]]; then
  echo "ERROR: product map file not found: $PRODUCT_MAP"
  exit 1
fi

if [[ ! -f "$REVIEW_FILE" ]]; then
  echo "ERROR: review file not found: $REVIEW_FILE"
  exit 1
fi

echo
echo "1) Shopify product sync"
python3 scripts/shopify_product_sync.py \
  --snapshot "$SNAPSHOT" \
  --product-map "$PRODUCT_MAP" \
  --mapped-only \
  --commit

echo
echo "2) Shopify inventory sync"
python3 scripts/shopify_inventory_sync.py \
  --snapshot "$SNAPSHOT" \
  --product-map "$PRODUCT_MAP" \
  --commit

echo
echo "3) Apply approved content"
python3 scripts/apply_product_content.py \
  --review-file "$REVIEW_FILE" \
  --commit

echo
echo "Demo completed successfully."