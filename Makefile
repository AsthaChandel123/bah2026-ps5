# ──────────────────────────────────────────────────────────────────────────
# Bharat Climate Twin — Makefile
# AI-Powered Digital Twin of India's Climate (ISRO BAH 2026, PS5)
#
# Common flows:
#   make install            # python deps (pipeline + backend) + frontend npm
#   make sample             # build offline-demo serving artifacts (synthetic)
#   make train              # train the AI ensemble -> metrics.json + forecast.json
#   make backend            # run FastAPI on :8000
#   make frontend           # run Next.js dev server on :3000
#   make demo               # docker compose up --build (full stack)
#
# The `sample` target is guaranteed to work with the Python standard library
# alone (no numpy/xarray), so the demo data can always be (re)built.
# ──────────────────────────────────────────────────────────────────────────

PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help install pipeline sample train backend frontend build demo verify clean

help: ## Show this help
	@echo "Bharat Climate Twin — make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python deps (pipeline + backend) and frontend npm packages
	$(PYTHON) -m pip install -r pipeline/requirements.txt
	$(PYTHON) -m pip install -r backend/requirements.txt
	cd frontend && npm install

pipeline: ## Run the full pipeline in SYNTHETIC mode (zero-network, stdlib-only)
	$(PYTHON) -m pipeline.run_pipeline --mode synthetic

sample: ## Generate the offline-demo serving artifacts (SYNTHETIC, stdlib-only)
	$(PYTHON) -m pipeline.run_pipeline --mode synthetic

train: ## Train the tiered AI ensemble -> data/.../{metrics,forecast}.json (+ mirrors)
	$(PYTHON) -m models.train

backend: ## Start the FastAPI O(1) serving API on :8000
	cd backend && $(PYTHON) -m uvicorn app.main:app --port 8000

frontend: ## Start the Next.js dashboard dev server on :3000
	cd frontend && npm run dev

build: ## Production build of the Next.js dashboard (must exit 0 cleanly)
	cd frontend && npm run build

demo: ## Full-stack demo via Docker (backend :8000 + frontend :3000)
	docker compose up --build

verify: ## Compile pipeline modules and confirm artifacts are valid JSON
	$(PYTHON) -m py_compile pipeline/*.py pipeline/ingest/*.py
	@echo "pipeline modules compile OK"
	$(PYTHON) -c "import json,glob; [json.loads(open(f).read()) for f in glob.glob('data/processed/sample/*.json')]; print('serving artifacts are valid JSON')"

clean: ## Remove generated artifacts, build output, and Python caches (keeps source)
	rm -f data/processed/sample/*.json frontend/public/data/*.json
	rm -rf data/processed/cube*.zarr data/processed/cog
	rm -rf frontend/.next frontend/out
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@echo "cleaned generated artifacts + caches"
