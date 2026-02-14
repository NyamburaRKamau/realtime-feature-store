.PHONY: help install start stop test benchmark clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dependencies
	pip install -r requirements.txt

start: ## Start feature store (docker-compose)
	docker-compose up -d
	@echo "✅ Feature store started!"
	@echo "   Feature Server: http://localhost:8000"
	@echo "   Redis: localhost:6379"
	@echo "   API Docs: http://localhost:8000/docs"

stop: ## Stop feature store
	docker-compose down

logs: ## View logs
	docker-compose logs -f

test: ## Run all tests
	pytest tests/ -v

benchmark: ## Run latency benchmarks
	pytest tests/test_latency.py -v -s

example: ## Run example workflow
	python -m examples.example_usage

generate-data: ## Generate sample data
	python -m examples.sample_data

compute-features: ## Compute features offline
	python -m offline_store.compute_features

sync-features: ## Sync offline features to online store
	python -m offline_store.sync_to_online

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf data/

restart: stop start ## Restart feature store

status: ## Check feature store status
	@curl -s http://localhost:8000/health | python -m json.tool || echo "Feature server not running"
