.PHONY: install server test clean lint test-live reset-local windows-ec2 windows-ec2-stop

# Install dependencies
install:
	uv sync --all-groups --all-extras

# Run server in dev mode (installs all extras so connector drivers are available)
server:
	uv sync --all-extras
	uv run mc-bridge | tee server.log 2>&1

# Run tests
test:
	uv run pytest -v

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
	@echo "Cleared certs and config. Run 'make server' to test first-time setup."

# Windows EC2 testing (configure in .envrc, see .envrc.template)
WINDOWS_STATE_FILE := .windows-ec2-state

# Launch a Windows EC2 instance for testing
windows-ec2:
	@if [ -f $(WINDOWS_STATE_FILE) ]; then \
		echo "Instance already exists. Run 'make windows-ec2-stop' first."; \
		cat $(WINDOWS_STATE_FILE); \
		exit 1; \
	fi
	@echo "Getting your public IP..."
	$(eval MY_IP := $(shell curl -s https://checkip.amazonaws.com))
	@echo "Creating security group..."
	$(eval SG_ID := $(shell aws ec2 create-security-group --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--group-name mc-bridge-windows-test-$$$$ --description "RDP for mc-bridge Windows testing" \
		--vpc-id $(WINDOWS_VPC) --query 'GroupId' --output text))
	@aws ec2 authorize-security-group-ingress --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--group-id $(SG_ID) --protocol tcp --port 3389 --cidr $(MY_IP)/32 > /dev/null
	@echo "Launching Windows instance..."
	$(eval INSTANCE_ID := $(shell aws ec2 run-instances --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--image-id $(WINDOWS_AMI) --instance-type $(WINDOWS_INSTANCE_TYPE) \
		--key-name $(WINDOWS_KEY_NAME) --security-group-ids $(SG_ID) \
		--subnet-id $(WINDOWS_SUBNET) --associate-public-ip-address \
		--tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=mc-bridge-windows-test}]' \
		--query 'Instances[0].InstanceId' --output text))
	@echo "Instance $(INSTANCE_ID) launching, waiting for it to run..."
	@aws ec2 wait instance-running --profile $(AWS_PROFILE) --region $(AWS_REGION) --instance-ids $(INSTANCE_ID)
	$(eval PUBLIC_IP := $(shell aws ec2 describe-instances --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--instance-ids $(INSTANCE_ID) --query 'Reservations[0].Instances[0].PublicIpAddress' --output text))
	@echo "$(INSTANCE_ID) $(SG_ID)" > $(WINDOWS_STATE_FILE)
	@echo ""
	@echo "Instance running! Waiting ~4 min for password..."
	@sleep 240
	$(eval PASSWORD := $(shell aws ec2 get-password-data --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--instance-id $(INSTANCE_ID) --priv-launch-key ~/.ssh/$(WINDOWS_KEY_NAME).pem \
		--query 'PasswordData' --output text))
	@echo "========================================"
	@echo "Windows EC2 Ready"
	@echo "========================================"
	@echo "IP:       $(PUBLIC_IP)"
	@echo "User:     Administrator"
	@echo "Password: $(PASSWORD)"
	@echo "========================================"
	@echo "Connect via Microsoft Remote Desktop"

# Terminate Windows EC2 instance and clean up
windows-ec2-stop:
	@if [ ! -f $(WINDOWS_STATE_FILE) ]; then \
		echo "No instance state file found. Nothing to stop."; \
		exit 0; \
	fi
	$(eval INSTANCE_ID := $(shell cut -d' ' -f1 $(WINDOWS_STATE_FILE)))
	$(eval SG_ID := $(shell cut -d' ' -f2 $(WINDOWS_STATE_FILE)))
	@echo "Terminating instance $(INSTANCE_ID)..."
	@aws ec2 terminate-instances --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--instance-ids $(INSTANCE_ID) > /dev/null
	@echo "Waiting for termination..."
	@aws ec2 wait instance-terminated --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--instance-ids $(INSTANCE_ID)
	@echo "Deleting security group $(SG_ID)..."
	@aws ec2 delete-security-group --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		--group-id $(SG_ID) > /dev/null
	@rm -f $(WINDOWS_STATE_FILE)
	@echo "Done. Instance and security group deleted."

# Show help
help:
	@echo "Available targets:"
	@echo "  install          - Install dependencies"
	@echo "  server           - Run server in dev mode"
	@echo "  test             - Run tests"
	@echo "  clean            - Clean build artifacts"
	@echo "  lint             - Run linter"
	@echo "  format           - Format code"
	@echo "  test-cors        - Test CORS headers"
	@echo "  test-query       - Test query endpoint"
	@echo "  test-live        - Live test connectors from mc-bridge.testing.yaml [CONNECTOR=<id>]"
	@echo "  reset-local      - Remove local config and certs for first-time testing"
	@echo "  windows-ec2      - Launch Windows EC2 for testing (uses AWS profile=dev)"
	@echo "  windows-ec2-stop - Terminate Windows EC2 and clean up"
