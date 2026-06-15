"""TrainGen discovery — Layer 1 (Extract) so far. See docs/DISCOVERY.md.

Layer 1 is deterministic: no LLM, no live crawl. It reads the FastAPI OpenAPI spec and
the Next.js app/ tree and emits feature_inventory.json (docs/FEATURE_INVENTORY.md).
"""
