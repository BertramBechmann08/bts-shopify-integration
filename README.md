# BTS ↔ Shopify Integration Prototype

This repository contains a Python integration prototype between BTSWholesaler and Shopify.

The goal of the integration is to support a dropshipping workflow where:

1. BTS products are synced to Shopify
2. Shopify prices and stock are updated from BTS
3. Shopify orders can be forwarded to BTS
4. BTS ships the order directly to the customer
5. Tracking information can later be returned to Shopify

--------------------------------------------------

CURRENT STATUS

The catalog side of the integration is working.

Implemented:

- BTS API client
- BTS catalog snapshot sync
- realtime stock and price enrichment
- Shopify product create/update sync
- Shopify inventory sync
- local Shopify product mapping by EAN
- title normalization
- rule-based product content generation
- content apply flow to Shopify
- BTS order validation and creation prototype
- BTS order mapping and tracking lookup
- Shopify API rate-limit handling
- manual demo script

Partially implemented / foundation exists:

- Shopify → BTS order handoff
- BTS tracking → Shopify fulfillment update

Not yet automated:

- scheduled sync jobs
- webhook-driven order automation
- automatic fulfillment / tracking updates in production

The system currently runs manually via scripts.

--------------------------------------------------

PROJECT STRUCTURE

Stack/

bts/
    client.py
    store.py

catalog/
    filters.py
    io.py
    normalize.py
    pricing.py
    product_data.py

shopify/
    client.py
    store.py
    order_store.py

scripts/
    apply_product_content.py
    bts_catalog_sync.py
    bts_order_dryrun.py
    bts_tracking_check.py
    export_snapshot_to_excel.py
    generate_product_content.py
    rewrite_product_content_ai.py
    shopify_inventory_sync.py
    shopify_order_to_bts.py
    shopify_product_sync.py
    shopify_test.py
    shopify_tracking_update.py

data/
    product_map.json
    order_map.json
    content_review.json
    content_review_existing.json
    bts_snapshot_*.json

docs/
    order_flow.md
    content_flow.md

.env
.env.example
requirements.txt
README.md
.gitignore

--------------------------------------------------

SETUP

Install dependencies:

pip install -r requirements.txt

Create a .env file:

BTS_API_TOKEN=your_bts_token_here
SHOPIFY_SHOP=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=your_shopify_admin_token
OPENAI_API_KEY=optional_for_ai_rewrite

Optional environment variables:

BTS_API_BASE_URL=https://api.btswholesaler.com/v1/api
BTS_HTTP_TIMEOUT_SECONDS=60
OPENAI_MODEL=gpt-5.4

--------------------------------------------------

BTS CATALOG SYNC

Fetch the BTS catalog and realtime stock/price data.

Run:

python3 scripts/bts_catalog_sync.py

What it does:

1. Fetches product catalog pages from BTS
2. Extracts EAN codes
3. Fetches realtime stock and price data in batches
4. Merges catalog data with realtime data
5. Saves a snapshot into the data/ directory

Example output:

data/bts_snapshot_20260309_165523.json

--------------------------------------------------

SHOPIFY PRODUCT SYNC

Creates or updates Shopify products from the BTS snapshot.

Run:

python3 scripts/shopify_product_sync.py \
  --snapshot data/bts_snapshot_20260309_165523.json \
  --product-map data/product_map.json \
  --mapped-only \
  --commit

What it does:

- matches products by EAN
- creates Shopify products if needed
- updates title, vendor, price and SKU
- stores Shopify IDs in product_map.json

--------------------------------------------------

SHOPIFY INVENTORY SYNC

Updates Shopify inventory levels based on BTS stock.

Run:

python3 scripts/shopify_inventory_sync.py \
  --snapshot data/bts_snapshot_20260309_165523.json \
  --product-map data/product_map.json \
  --commit

What it does:

- finds Shopify inventory items from the mapping
- updates stock levels
- prevents overselling if stock is zero

--------------------------------------------------

PRODUCT CONTENT FLOW

Product titles and descriptions are generated and reviewed locally before being applied.

Step 1 – Generate base content:

python3 scripts/generate_product_content.py

Step 2 – Review content in:

data/content_review.json

Step 3 – Apply approved content to Shopify:

python3 scripts/apply_product_content.py \
  --review-file data/content_review_existing.json \
  --commit

--------------------------------------------------

AI CONTENT REWRITE (OPTIONAL)

AI can optionally improve generated content.

Run:

python3 scripts/rewrite_product_content_ai.py \
  --review-file data/content_review_existing.json \
  --out data/content_review_existing_ai.json

AI rewriting is optional and not required for normal operation.

--------------------------------------------------

ORDER FLOW

Real order:

python3 scripts/bts_order_dryrun.py \
  --order-file data/test_order.json \
  --commit

What it does:

1. Loads order data
2. Validates destination country
3. Checks stock availability
4. Requests shipping options
5. Builds a valid setCreateOrder payload
6. Sends the order to BTS

--------------------------------------------------

ORDER DEDUPLICATION

Orders are stored in:

data/order_map.json

Purpose:

- prevent duplicate BTS order creation
- map Shopify order IDs to BTS order numbers

--------------------------------------------------

TRACKING LOOKUP

Retrieve tracking information for stored BTS orders.

Run:

python3 scripts/bts_tracking_check.py

Later this can be used to update Shopify fulfillments.

--------------------------------------------------

DEMO SCRIPT

Run a full demo of the catalog pipeline:

./scripts/demo_sync.sh

The demo performs:

1. Shopify product sync
2. Shopify inventory sync
3. Product content application

--------------------------------------------------

IMPORTANT BTS LIMITATION

BTS does not provide a sandbox environment.

Safe testing approach:

- use payment_method=banktransfer
- order remains in Pending Payment
- order can be cancelled by the BTS account manager

--------------------------------------------------

CURRENT DEVELOPMENT APPROACH

The integration is being built in phases.

Phase 1  
BTS catalog + stock integration

Phase 2  
Shopify product + inventory sync

Phase 3  
Content generation and management

Phase 4 (next)  
Shopify order → BTS automation  
BTS tracking → Shopify fulfillment updates

--------------------------------------------------

SUMMARY

The repository currently provides a working BTS → Shopify catalog pipeline.

Products, prices and stock can already be synchronized.

Order automation and fulfillment tracking are planned as the next phase once the catalog setup is finalized.