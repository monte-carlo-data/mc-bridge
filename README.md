# MC Bridge

Local bridge for Monte Carlo SaaS to connect to customer data sources.

## Overview

MC Bridge runs locally and provides an HTTP API (localhost:8765) that the MC web app can communicate with. It connects to Snowflake using browser-based SSO authentication.

## Installation

### Quick Start (uvx)

```bash
# Run directly without installing
uvx --from git+https://github.com/monte-carlo-data/mc-bridge.git mc-bridge-server
```

If no configuration exists, you'll see setup instructions.

### Local Development

```bash
make install
```

## Configuration

Edit `~/.montecarlodata/mc-bridge.yaml`:

```yaml
connectors:
  my-snowflake:
    account: myaccount.us-east-1
    user: user@company.com
    warehouse: COMPUTE_WH
    database: MY_DB       # optional
    schema: PUBLIC        # optional
    role: MY_ROLE         # optional

  # multiple connectors supported
  prod-snowflake:
    account: prod.us-east-1
    user: user@company.com
    warehouse: PROD_WH
```

## Usage

```bash
# Start server (dev mode)
make server

# Test CORS
make test-cors

# Test query
make test-query
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/connectors` | GET | List connectors |
| `/api/v1/connectors/{id}` | GET | Get connector |
| `/api/v1/connectors/{id}/test` | POST | Test connection (SSO) |
| `/api/v1/query` | POST | Execute SQL |

## Development

```bash
make test      # Run tests
make lint      # Run linter
make format    # Format code
```

## Building Standalone App

```bash
make build     # Build app
make open      # Open built app
# Output: dist/MC Bridge.app
```

## Security

- Binds to `127.0.0.1` only
- CORS restricted to `*.getmontecarlo.com`
- No credentials stored - uses Snowflake browser SSO

