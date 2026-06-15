.PHONY: install seed run-one selftest extract test clean

install:   ## python deps + Chromium
	pip install -r requirements.txt
	python -m playwright install chromium

seed:      ## reset demo tenant to a known state (BLUEPRINT §11)
	./scripts/reset_demo_tenant.sh

run-one:   ## v0.1 target: one scenario, BG only
	python run.py --scenario add-partner-profile --lang bg

selftest:  ## prove the timing model offline (no platform/browser needed)
	python -m tests.test_timing

extract:   ## Layer 1 — build feature_inventory.json (config or TRAINGEN_OPENAPI_URL/TRAINGEN_FRONTEND_APP)
	python -m traingen.discovery.extract

synthesize: ## Layer 2 — drafts.yaml from the inventory (needs anthropic + ANTHROPIC_API_KEY)
	python -m traingen.discovery.synthesize_cli

test:      ## run all offline tests
	python -m tests.test_timing
	python -m tests.test_extract
	python -m tests.test_synthesize

clean:
	rm -rf out/*
