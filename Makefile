.PHONY: install server test build clean lint test-live reset-local

# Install dependencies
install:
	uv sync --all-groups --all-extras

# Run server in dev mode (installs all extras so connector drivers are available)
server:
	uv sync --all-extras
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
	@curl -sk -X OPTIONS https://127.0.0.1:8765/health \
		-H "Origin: https://local.getmontecarlo.com:3000" \
		-H "Access-Control-Request-Method: GET" | head -12
	@echo "\n=== GET /health ==="
	@curl -sk https://127.0.0.1:8765/health

# Test query
test-query:
	curl -sk -X POST https://127.0.0.1:8765/api/v1/query \
		-H "Content-Type: application/json" \
		-d '{"connector_id": "snowflake-dev", "sql": "SELECT CURRENT_USER()"}'

# Live test connectors using mc-bridge.testing.yaml
# Usage: make test-live [CONNECTOR=<id>]
test-live:
	uv run python scripts/test_live.py $(CONNECTOR)

# Remove local config + certs to test first-time setup
reset-local:
	rm -rf ~/.montecarlodata/certs
	rm -f ~/.montecarlodata/mc-bridge.yaml
	security delete-certificate -c "MC Bridge Local CA" 2>/dev/null || true
	@echo "Cleared certs, config, and keychain trust. Run 'make server' to test first-time setup."

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
	@echo "  test-live   - Live test connectors from mc-bridge.testing.yaml [CONNECTOR=<id>]"
	@echo "  reset-local - Remove local config, certs, and keychain trust for first-time testing"
