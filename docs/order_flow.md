# BTS ↔ Shopify Integration: Order Flow

This document describes the intended integration workflow between BTSWholesaler and Shopify.

--------------------------------------------------

GOAL

The integration should support:

1. Syncing products, stock, and prices from BTS to Shopify
2. Sending Shopify orders to BTS for dropshipping
3. Retrieving tracking information from BTS
4. Updating Shopify orders with tracking information

--------------------------------------------------

IMPORTANT NOTE: NO SANDBOX

BTS does not provide a sandbox environment.

Any call to:

POST /v1/api/setCreateOrder

creates a real order.

For safer testing BTS recommends:

payment_method = banktransfer

This leaves the order in "Pending Payment" state so it can be cancelled.

--------------------------------------------------

A. PRODUCT CATALOG SYNC (BTS → SHOPIFY)

STEP 1 — FETCH PRODUCT CATALOG

Endpoint:

GET /v1/api/getListProducts

Parameters:

page  
page_size  

Returns:

products[]  
pagination  

Typical product fields:

ean  
name  
manufacturer  
image  
categories  
price  
stock  

Pagination fields:

total_pages  
has_next_page  
total_products  

--------------------------------------------------

STEP 2 — FETCH REALTIME STOCK AND PRICE

Endpoint:

GET /v1/api/getProductStock

BTS expects array parameters:

product_sku[]=EAN1  
product_sku[]=EAN2  

Returns per SKU:

stock  
price  
availability  
last_updated  

The integration merges this data with catalog data and stores a local snapshot.

Current prototype output:

data/bts_snapshot_*.json

--------------------------------------------------

B. ORDER FLOW (SHOPIFY → BTS)

STEP 1 — VALIDATE ORDER

Before creating an order the integration should validate:

destination country is supported  
requested SKUs exist  
requested quantities are in stock  

Endpoints used:

GET /v1/api/getCountries  
GET /v1/api/getProductStock  

--------------------------------------------------

STEP 2 — GET SHIPPING OPTIONS

Endpoint:

GET /v1/api/getShippingPrices

Parameters:

address[country_code]  
address[postal_code]  

products[0][sku]  
products[0][quantity]  
products[1][sku]  
products[1][quantity]  

Returns shipping options such as:

id  
company_name  
shipping_cost  
delivery_time  
free_shipping  

The integration selects one shipping_cost_id.

--------------------------------------------------

STEP 3 — CREATE BTS ORDER

Endpoint:

POST /v1/api/setCreateOrder

Content-Type:

application/x-www-form-urlencoded

Typical fields:

payment_method  
shipping_cost_id  
client_name  
address  
postal_code  
city  
country_code  
telephone  
dropshipping=1  

products[i][sku]  
products[i][quantity]  

--------------------------------------------------

STEP 4 — READ ORDER

Endpoint:

GET /v1/api/getOrder

Parameter:

order_number

Used to verify order creation and inspect order status.

--------------------------------------------------

STEP 5 — RETRIEVE TRACKING

Endpoint:

GET /v1/api/getTrackings

Parameter style:

order_number[]=...

Tracking information becomes available after BTS ships the order.

--------------------------------------------------

INTENDED END-TO-END FLOW

PRODUCT SYNC

BTS getListProducts + getProductStock  
→ Python sync script  
→ Shopify products and inventory

ORDER SYNC

Shopify order  
→ Python integration  
→ BTS getShippingPrices  
→ BTS setCreateOrder

TRACKING SYNC

BTS getTrackings  
→ Python integration  
→ Shopify fulfillment update

--------------------------------------------------

CURRENT PROTOTYPE STATUS

Implemented:

BTS API client  
catalog sync script  
stock batching  
order dry-run script  
country validation  
stock validation  
shipping lookup  
order payload generation  
order deduplication  
tracking lookup

Not implemented yet:

Shopify Admin API integration  
Shopify product creation  
Shopify order ingestion  
Shopify fulfillment tracking updates