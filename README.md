# MC Bridge

Local bridge for Monte Carlo SaaS to connect to customer data sources.

## Overview

MC Bridge runs locally and provides an HTTP API (localhost:8765) that the MC web app can communicate with. It connects to Snowflake, BigQuery, and Redshift using the same connection types and auth methods as dbt.

## Installation

### Quick Start (uvx)

```bash
# Snowflake only
uvx --from "mc-bridge[snowflake] @ git+https://github.com/monte-carlo-data/mc-bridge.git" mc-bridge-server

# All warehouses
uvx --from "mc-bridge[all] @ git+https://github.com/monte-carlo-data/mc-bridge.git" mc-bridge-server
```

If no configuration exists, you'll see setup instructions. If `~/.dbt/profiles.yml` exists, mc-bridge will offer to import your dbt connections (Snowflake, BigQuery, and Redshift).

### Local Development

```bash
make install
```

## Configuration

Edit `~/.montecarlodata/mc-bridge.yaml`:

```yaml
connectors:
  # Snowflake — browser SSO (default)
  my-snowflake:
    account: myaccount.us-east-1
    user: user@company.com
    warehouse: COMPUTE_WH
    database: MY_DB           # optional
    schema: PUBLIC            # optional
    role: MY_ROLE             # optional
    # method: externalbrowser # default — opens browser for SSO
    # method: password        # requires: password
    # method: keypair         # requires: private_key_path (or private_key)

  # BigQuery — Application Default Credentials
  my-bigquery:
    type: bigquery
    project: my-gcp-project
    dataset: my_dataset       # optional
    location: US              # optional
    # method: oauth           # default — uses gcloud auth application-default login
    # method: service-account # requires: keyfile

  # Redshift — password auth
  my-redshift:
    type: redshift
    host: my-cluster.us-east-1.redshift.amazonaws.com
    user: admin
    database: mydb
    password: mypassword
    schema: public            # optional
    # method: database        # default — user/password
    # method: iam             # uses AWS credential chain, optional: iam_profile, cluster_id, region
```

Snowflake configs don't require a `type` field (inferred from `account`/`warehouse` fields for backwards compatibility).

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
| `/api/v1/connectors/{id}/test` | POST | Test connection |
| `/api/v1/query` | POST | Execute SQL |

## Development

```bash
make test      # Run tests
make lint      # Run linter
make format    # Format code
```

## Security

- Binds to `127.0.0.1` only
- CORS restricted to `*.getmontecarlo.com`
- Browser SSO and ADC store no credentials locally
- Password and keyfile-based auth methods reference credentials in config
