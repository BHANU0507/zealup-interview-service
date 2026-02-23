#!/usr/bin/env python
"""Setup script to install Playwright browsers"""
import subprocess
import sys

try:
    from playwright.sync_api import sync_playwright
    print("Installing Playwright browsers...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("✓ Playwright setup complete!")
except Exception as e:
    print(f"Error during setup: {e}")
    sys.exit(1)
