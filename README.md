# BTS ↔ Shopify Integration Prototype

This repository contains a Python prototype integration with the BTSWholesaler API for a Shopify-based e-commerce setup.

The goal of the integration is to support a dropshipping workflow where:

1. BTS products are synced to Shopify
2. Shopify orders are forwarded to BTS
3. BTS ships the order directly to the customer
4. Tracking information is returned to Shopify

--------------------------------------------------

CURRENT SCOPE

The current repository focuses on the BTS side of the integration.

Implemented:

- BTS API client
- Catalog sync
- Realtime stock batching
- Order validation
- Shipping lookup
- Safe order dry-run flow
- Optional real order creation (--commit)
- Local order deduplication
- Tracking lookup

Not implemented yet:

- Shopify product creation
- Shopify inventory sync
- Shopify order ingestion
- Shopify fulfillment tracking updates

--------------------------------------------------

PROJECT STRUCTURE

Stack/

bts_client.py  
Reusable BTS API client

bts_catalog_sync.py  
Fetches the BTS catalog and realtime stock data and saves a local snapshot

bts_order_dryrun.py  
Demonstrates the BTS order creation workflow (dry-run by default)

bts_tracking_check.py  
Checks tracking information for created BTS orders

bts_store.py  
Minimal local persistence for order mappings

README.md  
Project documentation

requirements.txt  
Python dependencies

.env  
Local environment variables

.env.example  
Example environment configuration

.gitignore  
Git ignore rules

data/

test_order.json  
Example order input

order_map.json  
Mapping between external order IDs and BTS order numbers

bts_snapshot_*.json  
Catalog snapshots

docs/

order_flow.md  
Documentation describing the intended integration flow

scripts/

run_demo.sh  
Helper script to run a quick prototype demonstration

--------------------------------------------------

BTS API ENDPOINTS USED

Catalog and stock:

GET /v1/api/getListProducts  
GET /v1/api/getProductChanges  
GET /v1/api/getProductStock  
GET /v1/api/getFeedStatus  

Orders and shipping:

GET /v1/api/getCountries  
GET /v1/api/getShippingPrices  
POST /v1/api/setCreateOrder  
GET /v1/api/getOrder  
GET /v1/api/getTrackings  

Authentication:

Authorization: Bearer <BTS_API_TOKEN>

--------------------------------------------------

SETUP

Install dependencies:

pip install -r requirements.txt

Create a .env file:

BTS_API_TOKEN=your_bts_token_here

Optional environment variables:

BTS_API_BASE_URL=https://api.btswholesaler.com/v1/api  
BTS_HTTP_TIMEOUT_SECONDS=60

--------------------------------------------------

CATALOG SYNC

Run:

python3 bts_catalog_sync.py

What it does:

1. Fetches product catalog pages from BTS
2. Extracts EAN codes
3. Fetches realtime stock and price data in batches
4. Merges catalog data with realtime data
5. Saves a snapshot into the data/ directory

Example output:

data/bts_snapshot_20260305_210000.json

--------------------------------------------------

ORDER FLOW PROTOTYPE

Run:

python3 bts_order_dryrun.py --order-file data/test_order.json

What it does:

1. Loads order data from JSON
2. Validates destination country
3. Validates stock availability
4. Requests shipping options
5. Chooses a shipping method
6. Builds a valid setCreateOrder payload
7. Prints the payload without creating a real order

Create a real BTS order:

python3 bts_order_dryrun.py --order-file data/test_order.json --commit

Important:

The script uses payment_method=banktransfer for safer testing.  
BTS has no sandbox environment.  
Real orders are only created when using --commit.

--------------------------------------------------

ORDER DEDUPLICATION

The prototype stores a mapping in:

data/order_map.json

Purpose:

- prevent duplicate BTS order creation
- support future mapping between Shopify order IDs and BTS order numbers

--------------------------------------------------

TRACKING LOOKUP

Run:

python3 bts_tracking_check.py

This retrieves tracking information for stored BTS orders.

--------------------------------------------------

IMPORTANT BTS LIMITATION

BTS does not provide a sandbox environment.

Recommended safe testing approach:

- use payment_method=banktransfer
- order remains in Pending Payment
- order can be cancelled by the BTS account manager

--------------------------------------------------

CURRENT STATUS

Working:

- catalog fetch
- stock fetch
- shipping lookup
- order payload generation
- optional real order creation
- local order deduplication
- tracking lookup

Pending:

- Shopify Admin API access
- Shopify product sync
- Shopify order ingestion
- Shopify fulfillment tracking updates

--------------------------------------------------

NOTES

This project focuses on validating the BTS integration first before connecting it to Shopify.

Safe development approach:

- freely use GET endpoints
- keep order creation behind the --commit flag
- avoid real BTS orders unless necessary