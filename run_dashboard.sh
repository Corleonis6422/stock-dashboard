#!/bin/bash

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "================================================="
echo " Starting SOXL Dashboard Local CORS Proxy Server"
echo "================================================="

# Check if port 8080 is already in use
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Port 8080 is already in use. Local proxy might already be running."
else
    echo "Starting local CORS proxy on http://localhost:8080..."
    python3 "$DIR/local_proxy.py" 8080 > /dev/null 2>&1 &
    PROXY_PID=$!
    sleep 1
fi

echo "Opening SOXL Dashboard in default browser..."
if command -v open >/dev/null 2>&1; then
    open "http://localhost:8080/"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:8080/"
fi

echo "================================================="
echo "Dashboard is running at http://localhost:8080/"
echo "================================================="

