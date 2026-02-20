"""Main entry point for MC Bridge - macOS menu bar application."""

import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

import rumps
import uvicorn

from mc_bridge import __version__


def get_resource_path(relative_path: str) -> str | None:
    """Get path to resource, works for dev and PyInstaller bundle."""
    # Check multiple locations for the resource
    candidates = []

    # PyInstaller onefile mode
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / relative_path)

    # PyInstaller .app bundle - resources in Contents/Resources
    if getattr(sys, "frozen", False):
        # sys.executable is Contents/MacOS/mc-bridge
        bundle_dir = Path(sys.executable).parent.parent / "Resources"
        candidates.append(bundle_dir / relative_path)

    # Dev mode - relative to project root
    candidates.append(Path(__file__).parent.parent / relative_path)

    for path in candidates:
        if path.exists():
            return str(path)
    return None


def safe_notification(title: str, subtitle: str, message: str) -> None:
    """Send notification if possible, silently fail otherwise."""
    try:
        rumps.notification(title=title, subtitle=subtitle, message=message)
    except RuntimeError:
        # Notifications unavailable outside .app bundle - that's okay
        pass

# Default server configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class MCBridgeApp(rumps.App):
    """macOS menu bar application for MC Bridge."""

    @staticmethod
    def _get_icon_path() -> str | None:
        """Get path to menu bar icon."""
        return get_resource_path("resources/icon.png")

    def __init__(self) -> None:
        icon_path = self._get_icon_path()
        super().__init__("MC Bridge", icon=icon_path, quit_button=None)

        self.server_thread: threading.Thread | None = None
        self.server_running = False

        # Build menu
        self.menu = [
            rumps.MenuItem("Status: Stopped", callback=None),
            None,  # Separator
            rumps.MenuItem("Start Server", callback=self.toggle_server),
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            None,  # Separator
            rumps.MenuItem(f"Version {__version__}", callback=None),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        # Auto-start server
        self._start_server()

    def _start_server(self) -> None:
        """Start the FastAPI server in a background thread."""
        if self.server_running:
            return

        def run_server() -> None:
            from mc_bridge.server import app

            uvicorn.run(
                app,
                host=DEFAULT_HOST,
                port=DEFAULT_PORT,
                log_level="warning",
            )

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.server_running = True

        # Update menu
        self.menu["Status: Stopped"].title = f"Status: Running on port {DEFAULT_PORT}"
        self.menu["Start Server"].title = "Stop Server"

        safe_notification(
            title="MC Bridge",
            subtitle="Server Started",
            message=f"Listening on http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        )

    def _stop_server(self) -> None:
        """Stop the server (note: uvicorn doesn't gracefully stop in threads easily)."""
        # For a production app, we'd use a proper shutdown mechanism
        # For now, we just update the UI - the server keeps running until app quits
        self.server_running = False
        self.menu["Status: Stopped"].title = "Status: Stopped"
        self.menu["Start Server"].title = "Start Server"

        safe_notification(
            title="MC Bridge",
            subtitle="Server Stopped",
            message="The bridge server has been stopped",
        )

    @rumps.clicked("Start Server")
    def toggle_server(self, sender: Any) -> None:
        """Toggle server on/off."""
        if self.server_running:
            self._stop_server()
        else:
            self._start_server()

    @rumps.clicked("Open Dashboard")
    def open_dashboard(self, _: Any) -> None:
        """Open the dashboard in the default browser."""
        webbrowser.open(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health")

    @rumps.clicked("Quit")
    def quit_app(self, _: Any) -> None:
        """Quit the application."""
        rumps.quit_application()


def run_server_only() -> None:
    """Run just the HTTP server without menu bar (for development)."""
    from mc_bridge.server import app

    print(f"MC Bridge v{__version__}")
    print(f"Starting server on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level="info",
    )


def main() -> None:
    """Main entry point."""
    import sys

    # Use --server flag for server-only mode (dev friendly)
    if "--server" in sys.argv:
        run_server_only()
    else:
        app = MCBridgeApp()
        app.run()


if __name__ == "__main__":
    main()

