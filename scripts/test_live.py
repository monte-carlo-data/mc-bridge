#!/usr/bin/env python3
"""Live integration test for connectors using mc-bridge.testing.yaml.

Reads connector configs from mc-bridge.testing.yaml (same format as mc-bridge.yaml)
and runs connection, introspection, and query tests against each.

Usage:
  uv run python scripts/test_live.py                  # test all connectors
  uv run python scripts/test_live.py <connector-id>   # test a specific connector
"""

import sys
from pathlib import Path

from mc_bridge.config import ConfigManager
from mc_bridge.server import _create_connector

CONFIG_FILE = Path(__file__).parent.parent / "mc-bridge.testing.yaml"


def test_connector(connector_id: str, manager: ConfigManager) -> bool:
    config = manager.get_connector(connector_id)
    if not config:
        print(f"  Connector '{connector_id}' not found in config")
        return False

    connector = _create_connector(config)

    # Test connection
    print("  Testing connection...")
    result = connector.test_connection()
    print(f"  {result}")
    if not result.get("success"):
        print("  FAILED: Connection failed")
        return False

    # List databases
    print("  Listing databases...")
    databases = connector.list_databases()
    for db in databases[:10]:
        print(f"    {db}")
    if len(databases) > 10:
        print(f"    ... and {len(databases) - 10} more")

    # List tables in first database
    if databases:
        target_db = databases[0]
        schemas = connector.list_schemas(target_db)
        if schemas:
            target_schema = schemas[0]
            print(f"  Tables in {target_db}.{target_schema}:")
            tables = connector.list_tables(target_db, target_schema)
            for t in tables[:10]:
                print(f"    {t}")
            if len(tables) > 10:
                print(f"    ... and {len(tables) - 10} more")

    # Run a simple query
    print("  Running query: SELECT 1 AS num, 'hello' AS greeting")
    qr = connector.execute_query("SELECT 1 AS num, 'hello' AS greeting")
    print(f"    Columns: {qr.columns}")
    print(f"    Rows:    {qr.rows}")
    print(f"    Time:    {qr.execution_time_ms:.0f}ms")

    connector.disconnect()
    return True


def main() -> None:
    if not CONFIG_FILE.exists():
        print(f"Config not found: {CONFIG_FILE}")
        print("Copy mc-bridge.testing.yaml.template to mc-bridge.testing.yaml and fill in values.")
        sys.exit(1)

    manager = ConfigManager(config_file=CONFIG_FILE)
    connectors = manager.list_connectors()

    if not connectors:
        print("No connectors defined in mc-bridge.testing.yaml")
        sys.exit(1)

    # Filter to specific connector if requested
    filter_id = sys.argv[1] if len(sys.argv) > 1 else None
    if filter_id:
        connectors = [c for c in connectors if c.id == filter_id]
        if not connectors:
            print(f"Connector '{filter_id}' not found. Available:")
            for c in manager.list_connectors():
                print(f"  {c.id} ({c.type})")
            sys.exit(1)

    passed = 0
    failed = 0
    for config in connectors:
        print(f"\n=== {config.id} ({config.type}) ===")
        if test_connector(config.id, manager):
            passed += 1
            print(f"  PASSED")
        else:
            failed += 1
            print(f"  FAILED")

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
