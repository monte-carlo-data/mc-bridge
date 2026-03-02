.PHONY: install server test build clean lint

# Install dependencies
install:
	uv sync --all-groups

# Run server in dev mode
server:
	uv run mc-bridge --server | tee server.log 2>&1

# Run tests
test:
	uv run pytest -v

# Build standalone macOS app
build:
	uv run pyinstaller mc_bridge.spec --clean -y

# Open built app
open:
	open "dist/MC Bridge.app"

# Clean build artifacts
clean:
	rm -rf build dist __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Run linter
lint:
	uv run ruff check mc_bridge tests
	uv run ruff format --check mc_bridge tests

# Format code
format:
	uv run ruff format mc_bridge tests

# Test CORS
test-cors:
	@echo "=== Preflight OPTIONS ==="
	@curl -si -X OPTIONS http://127.0.0.1:8765/health \
		-H "Origin: https://local.getmontecarlo.com:3000" \
		-H "Access-Control-Request-Method: GET" | head -12
	@echo "\n=== GET /health ==="
	@curl -s http://127.0.0.1:8765/health

# Test query
test-query:
	curl -s -X POST http://127.0.0.1:8765/api/v1/query \
		-H "Content-Type: application/json" \
		-d '{"connector_id": "snowflake-dev", "sql": "SELECT CURRENT_USER()"}'

# Show help
help:
	@echo "Available targets:"
	@echo "  install     - Install dependencies"
	@echo "  server      - Run server in dev mode"
	@echo "  test        - Run tests"
	@echo "  build       - Build standalone macOS app"
	@echo "  open        - Open built app"
	@echo "  clean       - Clean build artifacts"
	@echo "  lint        - Run linter"
	@echo "  format      - Format code"
	@echo "  test-cors   - Test CORS headers"
	@echo "  test-query  - Test query endpoint"
