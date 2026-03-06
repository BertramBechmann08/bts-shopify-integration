#!/usr/bin/env bash
set -e

echo ""
echo "==============================================="
echo "BTS ↔ Shopify Integration Prototype Demo"
echo "==============================================="
echo ""

echo "1) Catalog sync test (first 3 pages)"
python3 bts_catalog_sync.py --mode full --max-pages 3

echo ""
echo "2) Order dry run"
python3 bts_order_dryrun.py --order-file data/test_order.json

echo ""
echo "3) Tracking lookup"
python3 bts_tracking_check.py

echo ""
echo "Demo finished"
echo ""