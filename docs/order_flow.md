# BTS ↔ Shopify integration: Order flow (notes)

Formålet er at kunne:
1) Synkronisere produkter + stock/priser fra BTS
2) Sende Shopify-ordrer til BTS (dropshipping)
3) Hente tracking fra BTS og opdatere Shopify

## Vigtig note: ingen sandbox
BTS har ingen sandbox. API-kald til `setCreateOrder` opretter rigtige ordrer.
BTS anbefaler at teste med:
- `payment_method = banktransfer`
så ordren bliver “Pending Payment” og kan annulleres.

---

# A) Catalog + stock/pris (BTS → Shopify)

## 1) Hent katalog
Endpoint:
- GET `/v1/api/getListProducts`
Parametre:
- `page`
- `page_size`

Returnerer bl.a.:
- `products[]` (EAN, name, manufacturer, image, categories, price, stock)
- `pagination` (total_pages, has_next_page, total_products)

## 2) Hent realtime stock/pris for EANs
Endpoint:
- GET `/v1/api/getProductStock`

Vigtigt: BTS forventer array-parametre:
- `product_sku[]=EAN1`
- `product_sku[]=EAN2`
- ...

Returnerer pr EAN:
- `stock`
- `price`
- `availability`
- `last_updated`

Output gemmes lokalt som JSON snapshot i `data/`.

---

# B) Order flow (Shopify → BTS → tracking tilbage)

## Step 1 — Shipping prices
Endpoint:
- GET `/v1/api/getShippingPrices`

Parametre (nested):
- `address[country_code]`
- `address[postal_code]`
- `products[0][sku]`
- `products[0][quantity]`
- `products[1][sku]`
- ...

Returnerer liste over muligheder, fx:
- `id`
- `company_name` (GLS/FedEx)
- `shipping_cost`
- `delivery_time`
- `free_shipping`

Vi vælger en `shipping_cost_id` (typisk GLS hvis pris er ens).

## Step 2 — Create order
Endpoint:
- POST `/v1/api/setCreateOrder`
Content-Type:
- `application/x-www-form-urlencoded`

Felter:
- `payment_method`
- `shipping_cost_id`
- `client_name`
- `address`
- `postal_code`
- `city`
- `country_code`
- `telephone`
- `dropshipping=1`
- `products[i][sku]`
- `products[i][quantity]`

## Step 3 — Read order (validering)
Endpoint:
- GET `/v1/api/getOrder`
Param:
- `order_number`

## Step 4 — Tracking
Endpoint:
- GET `/v1/api/getTrackings`
Param:
- `order_number`

Tracking kan først være tilgængelig efter BTS har afsendt.

---

# Lokal status (prototype)
- `bts_catalog_sync.py` kan hente katalog + realtime stock/pris og gemme snapshot.
- `bts_order_dryrun.py` kan hente shipping options og bygge korrekt payload til `setCreateOrder` uden at oprette ordre.