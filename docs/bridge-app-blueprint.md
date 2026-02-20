# Monte Carlo Bridge App - Implementation Blueprint

## 1. Overview

### Goal
Build a macOS menu bar application that acts as a secure bridge between the Monte Carlo SaaS platform and customer Snowflake instances.

### Core Requirements
- macOS menu bar app (Python + rumps)
- Local HTTP server (FastAPI) on localhost
- Snowflake connector with browser-based SSO auth
- Configuration UI for managing connectors
- Query execution endpoint for MC SaaS integration

### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                    MC Bridge App (macOS)                        │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Menu Bar    │    │  FastAPI     │    │  Snowflake       │  │
│  │  (rumps)     │◄──►│  Server      │◄──►│  Connector       │  │
│  │              │    │  :8765       │    │  (externalbrowser)│  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│         │                   ▲                                   │
│         ▼                   │                                   │
│  ┌──────────────┐           │ HTTP (localhost only)            │
│  │  Config      │           │                                   │
│  │  Storage     │           │                                   │
│  │  (~/.mc-bridge)          │                                   │
│  └──────────────┘           │                                   │
└─────────────────────────────┼───────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │  Browser (MC SaaS JavaScript) │
              │  https://getmontecarlo.com    │
              └───────────────────────────────┘
```

---

## 2. Project Structure

```
mc-bridge/
├── mc_bridge/
│   ├── __init__.py
│   ├── app.py              # Main entry point, rumps menu bar
│   ├── server.py           # FastAPI HTTP server
│   ├── config.py           # Configuration management
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py         # Base connector interface
│   │   └── snowflake.py    # Snowflake connector implementation
│   ├── models.py           # Pydantic models
│   └── security.py         # CORS, origin validation
├── tests/
│   ├── test_server.py
│   ├── test_connectors.py
│   └── test_config.py
├── resources/
│   └── icon.png                # Menu bar icon
├── pyproject.toml
├── setup.py                    # For py2app bundling
└── docs/
    └── bridge-app-blueprint.md
```

---

## 3. Implementation Steps

### Step 1: Project Setup & Dependencies

**Goal:** Initialize project structure with all required dependencies.

**Tasks:**
1. Create project skeleton with `uv init`
2. Add dependencies to `pyproject.toml`
3. Create package structure

**Dependencies:**
```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "rumps>=0.4.0",
    "snowflake-connector-python>=3.6.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "httpx>=0.26.0", "py2app>=0.28.0"]
```

---

### Step 2: Configuration Management

**Goal:** Implement secure storage and retrieval of connector configurations.

**Tasks:**
1. Create config directory at `~/.mc-bridge/`
2. Implement `ConnectorConfig` Pydantic model
3. Implement `ConfigManager` class for CRUD operations
4. Store configs as JSON (credentials never stored - SSO only)

**Key Code:**
```python
# models.py
class ConnectorConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    connector_type: Literal["snowflake"] = "snowflake"
    account: str           # e.g., "xy12345.us-east-1"
    user: str              # e.g., "user@company.com"
    warehouse: str
    database: str | None = None
    schema_name: str | None = None
    role: str | None = None
```

---

### Step 3: Snowflake Connector Implementation

**Goal:** Implement Snowflake connector with browser-based SSO authentication.

**Tasks:**
1. Create `BaseConnector` abstract class
2. Implement `SnowflakeConnector` class
3. Handle browser auth flow (`authenticator="externalbrowser"`)
4. Implement query execution with result serialization
5. Handle connection pooling/caching

**Key Code:**
```python
# connectors/snowflake.py
class SnowflakeConnector(BaseConnector):
    def connect(self) -> None:
        self._conn = snowflake.connector.connect(
            account=self.config.account,
            user=self.config.user,
            warehouse=self.config.warehouse,
            database=self.config.database,
            authenticator="externalbrowser",  # Opens browser for SSO
        )

    def execute_query(self, sql: str) -> QueryResult:
        cursor = self._conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return QueryResult(columns=columns, rows=rows)
```

---

### Step 4: FastAPI HTTP Server

**Goal:** Implement localhost HTTP server with all required endpoints.

**Tasks:**
1. Create FastAPI app with CORS middleware
2. Implement health endpoint
3. Implement connector CRUD endpoints
4. Implement query execution endpoint
5. Add origin validation security

**Endpoints:**
```
GET  /health                    → Health check
GET  /api/v1/connectors         → List all connectors
POST /api/v1/connectors         → Create connector
GET  /api/v1/connectors/{id}    → Get connector by ID
PUT  /api/v1/connectors/{id}    → Update connector
DELETE /api/v1/connectors/{id}  → Delete connector
POST /api/v1/connectors/{id}/test  → Test connection
POST /api/v1/query              → Execute SQL query
```

**Key Code:**
```python
# server.py
app = FastAPI(title="MC Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://getmontecarlo.com", "https://*.getmontecarlo.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

@app.post("/api/v1/query")
def execute_query(request: QueryRequest) -> QueryResponse:
    connector = connector_manager.get(request.connector_id)
    result = connector.execute_query(request.sql)
    return QueryResponse(columns=result.columns, rows=result.rows)
```

---

### Step 5: Security Layer

**Goal:** Implement security measures for localhost server.

**Tasks:**
1. CORS configuration restricting to MC domains
2. Origin header validation middleware
3. Optional local auth token (stored in config)
4. Request logging for audit trail

**Key Code:**
```python
# security.py
ALLOWED_ORIGINS = [
    "https://getmontecarlo.com",
    "https://app.getmontecarlo.com",
    "http://localhost:3000",  # Local MC development
]

@app.middleware("http")
async def validate_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and not any(fnmatch(origin, p) for p in ALLOWED_ORIGINS):
        return JSONResponse(status_code=403, content={"error": "Forbidden origin"})
    return await call_next(request)
```

---

### Step 6: Menu Bar App (rumps)

**Goal:** Create macOS menu bar application wrapper.

**Tasks:**
1. Create rumps app with menu items
2. Start/stop server from menu
3. Show connection status
4. Open configuration window
5. Run server in background thread

**Key Code:**
```python
# app.py
import rumps
import threading

class MCBridgeApp(rumps.App):
    def __init__(self):
        super().__init__("MC Bridge", icon="resources/icon.png")
        self.menu = [
            "Status: Running",
            None,  # Separator
            "Open Dashboard",
            "Connectors",
            None,
            "Start Server",
            "Stop Server",
        ]
        self.server_thread = None

    @rumps.clicked("Start Server")
    def start_server(self, _):
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        rumps.notification("MC Bridge", "", "Server started on port 8765")

    @rumps.clicked("Open Dashboard")
    def open_dashboard(self, _):
        webbrowser.open("http://localhost:8765/dashboard")
```

---

### Step 7: Local Dashboard UI

**Goal:** Simple web-based UI for managing connectors (served by FastAPI).

**Tasks:**
1. Serve static HTML/JS from FastAPI
2. Create connector management page
3. Create connection test page
4. Display server status and logs

**Approach:** Minimal HTML + vanilla JS, or use htmx for simplicity.

---

### Step 8: Testing

**Goal:** Comprehensive test coverage.

**Tasks:**
1. Unit tests for config manager
2. Unit tests for connectors (mocked Snowflake)
3. Integration tests for API endpoints (httpx + TestClient)
4. End-to-end test with real Snowflake (manual/CI)

**Key Code:**
```python
# tests/test_server.py
from fastapi.testclient import TestClient

def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

---

### Step 9: Packaging with py2app

**Goal:** Bundle as standalone macOS .app.

**Tasks:**
1. Create `setup.py` for py2app
2. Configure app metadata and icon
3. Bundle all dependencies
4. Test standalone app
5. Create DMG installer

**Key Code:**
```python
# setup.py
from setuptools import setup

APP = ['mc_bridge/app.py']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'resources/icon.icns',
    'plist': {
        'CFBundleName': 'MC Bridge',
        'CFBundleIdentifier': 'com.montecarlodata.bridge',
        'LSUIElement': True,  # Menu bar app (no dock icon)
    },
    'packages': ['mc_bridge', 'fastapi', 'uvicorn', 'snowflake'],
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
```

**Build command:**
```bash
python setup.py py2app
```

---

### Step 10: Distribution & Updates

**Goal:** Distribute app to users and handle updates.

**Tasks:**
1. Code sign with Apple Developer certificate
2. Notarize app for Gatekeeper
3. Create DMG installer
4. Implement auto-update mechanism (optional)
5. Documentation for installation

---

## 4. API Specification

### Health Check
```http
GET /health
Response: {"status": "ok", "version": "1.0.0", "connectors": 2}
```

### List Connectors
```http
GET /api/v1/connectors
Response: [
  {"id": "abc-123", "name": "Production", "connector_type": "snowflake", ...},
  ...
]
```

### Create Connector
```http
POST /api/v1/connectors
Body: {
  "name": "Production Snowflake",
  "connector_type": "snowflake",
  "account": "xy12345.us-east-1",
  "user": "analyst@company.com",
  "warehouse": "COMPUTE_WH",
  "database": "ANALYTICS"
}
Response: {"id": "abc-123", "name": "Production Snowflake", ...}
```

### Execute Query
```http
POST /api/v1/query
Body: {
  "connector_id": "abc-123",
  "sql": "SELECT * FROM users LIMIT 10"
}
Response: {
  "columns": ["id", "name", "email"],
  "rows": [[1, "Alice", "alice@co.com"], ...],
  "row_count": 10,
  "execution_time_ms": 234
}
```

---

## 5. Implementation Order

| Step | Description | Effort | Dependencies |
|------|-------------|--------|--------------|
| 1 | Project setup | 1h | None |
| 2 | Config management | 2h | Step 1 |
| 3 | Snowflake connector | 3h | Step 2 |
| 4 | FastAPI server | 3h | Step 2, 3 |
| 5 | Security layer | 2h | Step 4 |
| 6 | Menu bar app | 2h | Step 4 |
| 7 | Dashboard UI | 3h | Step 4 |
| 8 | Testing | 3h | All above |
| 9 | py2app packaging | 2h | All above |
| 10 | Distribution | 2h | Step 9 |

**Total estimated effort:** ~23 hours

---

## 6. Open Questions

1. **Auth token:** Should the bridge require a shared secret between MC SaaS and the bridge?
2. **Multi-connector queries:** Should a single query request support querying across multiple connectors?
3. **Query timeout:** What's the appropriate timeout for long-running queries?
4. **Result pagination:** How to handle large result sets? Stream or paginate?
5. **Audit logging:** Should we log all queries to a local file for compliance?

