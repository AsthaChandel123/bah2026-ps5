# ──────────────────────────────────────────────────────────────────────────
# Bharat Climate Twin — Makefile
# AI-Powered Digital Twin of India's Climate (ISRO BAH 2026, PS5)
#
# The `sample` / `pipeline` targets generate the offline-demo serving artifacts.
# `sample` is guaranteed to work with the Python standard library alone (no
# numpy/xarray), so the demo data can always be (re)built.
# ──────────────────────────────────────────────────────────────────────────

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help pipeline sample clean install backend frontend verify

help: ## Show this help
	@echo "Bharat Climate Twin — make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the (optional) real-ingestion Python dependencies
	$(PYTHON) -m pip install -r pipeline/requirements.txt

pipeline: ## Run the full pipeline in AUTO mode (probe real sources, fall back to synthetic)
	$(PYTHON) -m pipeline.run_pipeline --mode auto

sample: ## Generate the offline-demo serving artifacts (SYNTHETIC, zero-network, stdlib-only)
	$(PYTHON) -m pipeline.run_pipeline --mode synthetic

verify: ## Compile all pipeline modules and confirm artifacts conform to CONTRACT.md
	$(PYTHON) -m py_compile pipeline/*.py pipeline/ingest/*.py
	@echo "pipeline modules compile OK"
	$(PYTHON) -c "import json,glob; [json.loads(open(f).read()) for f in glob.glob('data/processed/sample/*.json')]; print('serving artifacts are valid JSON')"

clean: ## Remove generated artifacts and Python caches (keeps source)
	rm -f data/processed/sample/*.json frontend/public/data/*.json
	rm -rf data/processed/cube*.zarr data/processed/cog
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@echo "cleaned generated artifacts + caches"

# ── Stubs for the other workers (backend / frontend live in their own dirs) ──
backend: ## (stub) Start the FastAPI backend — see backend/ (added by the API worker)
	@echo "backend target stub — the FastAPI service lives under backend/ (ARCHITECTURE.md §10)."
	@echo "Once present:  cd backend && uvicorn app.main:app --reload"

frontend: ## (stub) Start the Next.js dashboard — see frontend/ (added by the UI worker)
	@echo "frontend target stub — the Next.js app lives under frontend/ (ARCHITECTURE.md §9)."
	@echo "Once present:  cd frontend && npm install && npm run dev"
