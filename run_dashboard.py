#!/usr/bin/env python3
"""
Cross-Platform Python Launcher for SOXL Stock Dashboard.
Runs local_proxy.py and opens the dashboard in the default browser.
"""
import os
import sys
import time
import webbrowser
import threading
from local_proxy import run as run_server

def main():
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    print("=================================================")
    print(" Starting SOXL Dashboard Local CORS Proxy Server")
    print("=================================================")

    url = f"http://localhost:{port}/"

    # Run proxy server in a daemon thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    time.sleep(1)
    print(f"\nOpening dashboard at {url} in your default browser...")
    webbrowser.open(url)

    print("\nPress Ctrl+C to stop the dashboard server.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server... Goodbye!")

if __name__ == '__main__':
    main()
