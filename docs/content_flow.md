# Product content flow

Goal:
Generate original Danish product copy for Shopify draft products without scraping or copying retailer descriptions directly.

Flow:
1. Read product facts from BTS snapshot
2. Generate Danish draft content
3. Review and edit content manually in `data/content_review.json`
4. Apply approved content to Shopify draft products

Rules:
- Do not copy product descriptions from other websites
- Do not translate source text 1:1 if wording is poor
- Do not invent unsupported claims
- Keep content short, factual, and commercial
- Products remain draft until reviewed

Files:
- `scripts/generate_product_content.py`
- `scripts/apply_product_content.py`
- `data/content_review.json`