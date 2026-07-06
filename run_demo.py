"""
Script khởi động demo SoundShield Flask cho Replit.
Mount tại /demo để phù hợp với reverse proxy.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))

from database import init_db
init_db()

from app import app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.exceptions import NotFound
from werkzeug.serving import run_simple

# Mount Flask tại /demo prefix
application = DispatcherMiddleware(NotFound(), {"/demo": app})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🎵 SoundShield Flask Demo running on port {port} at /demo")
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=False)
