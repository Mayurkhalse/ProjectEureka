.PHONY: dev test generate-data compose-up compose-down clean

dev:
	@echo "Running backend in pure headless mode (no frontend)..."
	uv run uvicorn eureka.api.main:app --app-dir backend/src --reload --port 8000

test:
	uv run pytest backend/tests/ -v

generate-data:
	uv run python backend/src/eureka/processor/generate_english_synthetic.py

compose-up:
	docker compose -f backend/docker-compose.yml up -d

compose-down:
	docker compose -f backend/docker-compose.yml down

clean:
	@echo "Cleaning temporary cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
