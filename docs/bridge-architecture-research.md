# Monte Carlo Bridge Application - Research Findings

## Overview

Build a local "bridge" application that enables the Monte Carlo SaaS platform to execute SQL queries against customer Snowflake instances through a secure local proxy.

---

## Key Question: How Can SaaS Communicate with Localhost?

**Answer: Yes, this is possible and widely used.** Several patterns exist:

### 1. Browser-to-Localhost (Recommended)

When a user loads the MC SaaS web app in their browser, **JavaScript running in the browser CAN make HTTP requests to `localhost`**. This is the pattern used by:

- **Figma** (Local Font Helper)
- **Slack** (Desktop app integration)
- **1Password** (Browser-to-desktop communication)
- **VS Code** (Remote development)

**How it works:**
```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Browser                           │
│  ┌─────────────────────────────────────┐                        │
│  │   MC SaaS Web App (JavaScript)      │                        │
│  │   https://getmontecarlo.com         │                        │
│  │                                     │                        │
│  │   fetch('http://localhost:8765/query', {...})               │
│  └──────────────────┬──────────────────┘                        │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      │ HTTP Request
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    User's Local Machine                         │
│  ┌─────────────────────────────────────┐                        │
│  │   MC Bridge App (localhost:8765)    │                        │
│  │   - Receives query request          │                        │
│  │   - Executes on Snowflake           │                        │
│  │   - Returns results                 │                        │
│  └──────────────────┬──────────────────┘                        │
│                     │                                           │
│                     ▼                                           │
│  ┌─────────────────────────────────────┐                        │
│  │   Snowflake (via SSO/Browser Auth)  │                        │
│  └─────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

### Security Considerations for Browser→Localhost

#### Mixed Content (HTTPS→HTTP)

**Challenge:** SaaS runs on HTTPS, localhost typically runs HTTP.

**Modern browser behavior:** Browsers now treat `localhost` as a "secure context" and allow HTTPS pages to fetch from `http://localhost`. This works in Chrome, Edge, Firefox, Safari (recent versions).

#### CORS Headers Required

The bridge must return proper CORS headers:
```python
Access-Control-Allow-Origin: https://getmontecarlo.com
Access-Control-Allow-Methods: POST, GET, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

#### Port Discovery

**Challenge:** How does the SaaS know which port the bridge is running on?

**Solutions:**
1. **Fixed port** (e.g., always 8765) - simple but may conflict
2. **Port range scanning** - try ports 8765-8775 until one responds
3. **Well-known file** - write port to `~/.mc-bridge/port`

### 2. Alternative: WebSocket Outbound Connection

Instead of SaaS→localhost, the bridge initiates a **persistent outbound WebSocket** to MC SaaS:

```
Bridge ──WebSocket──► wss://api.getmontecarlo.com/bridge
```

**Pros:** Works through firewalls, no port exposure
**Cons:** More complex, requires MC backend changes, always-on connection

### 3. Alternative: Polling Model

Bridge periodically polls MC SaaS for pending queries:
```
Bridge ──GET /pending-queries──► MC SaaS
```

**Pros:** Simpler than WebSocket
**Cons:** Latency, inefficient

---

## Recommended Architecture: Browser-to-Localhost

**Primary pattern:** JavaScript in MC SaaS UI makes direct HTTP calls to localhost bridge.

### Implementation Stack

| Component | Technology |
|-----------|------------|
| Mac App Framework | `rumps` (Python menu bar apps) |
| HTTP Server | `FastAPI` or `Flask` |
| Bundling | `py2app` (creates .app bundle) |
| Snowflake | `snowflake-connector-python` with `authenticator="externalbrowser"` |

---

## Bridge App Features

### Core Capabilities
1. **Menu bar app** - runs in background, accessible from menu bar
2. **Local HTTP server** - listens on localhost:8765
3. **Connector configuration UI** - add/edit Snowflake connections
4. **Query endpoint** - `/query` accepts SQL and returns results
5. **Health endpoint** - `/health` for connectivity checks

### API Endpoints

```
GET  /health              → {"status": "ok", "version": "1.0.0"}
GET  /connectors          → list configured connectors
POST /connectors          → add new connector
POST /query               → execute SQL query
```

### Snowflake Connection Config
```json
{
  "name": "production",
  "account": "xy12345.us-east-1",
  "user": "user@company.com",
  "warehouse": "COMPUTE_WH",
  "database": "ANALYTICS",
  "authenticator": "externalbrowser"
}
```

---

## Security Model

1. **Localhost only** - server binds to 127.0.0.1, not exposed externally
2. **CORS restricted** - only allows requests from `*.getmontecarlo.com`
3. **Origin verification** - validate Origin header on all requests
4. **Optional token** - bridge can require a local secret token
5. **No credentials stored** - Snowflake auth via browser SSO each session

---

## Distribution

### py2app Bundle
- Creates standalone `.app` bundle
- No Python installation required by user
- Can be notarized for macOS Gatekeeper
- DMG installer for easy distribution

---

## Next Steps

1. **Prototype** the bridge with FastAPI + rumps
2. **Test** browser→localhost communication from MC staging
3. **Design** the MC SaaS integration (JavaScript client)
4. **Bundle** with py2app and test distribution

