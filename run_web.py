#!/usr/bin/env python3
"""
Chamber Web Server Entry Point
Compatible with both Local development (port 8000) and Cloud platforms like Render/Railway (PORT env).
"""

import os
from web_gui.server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    run_server(host="0.0.0.0", port=port)
