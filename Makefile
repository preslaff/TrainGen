.PHONY: install seed run-one selftest clean

install:   ## python deps + Chromium
	pip install -r requirements.txt
	python -m playwright install chromium

seed:      ## reset demo tenant to a known state (BLUEPRINT §11)
	./scripts/reset_demo_tenant.sh

run-one:   ## v0.1 target: one scenario, BG only
	python run.py --scenario add-partner-profile --lang bg

selftest:  ## prove the timing model offline (no platform/browser needed)
	python -m tests.test_timing

clean:
	rm -rf out/*
