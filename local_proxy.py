import os
import sys
import ssl
import json
import time
import urllib.request
import urllib.parse
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Directory containing this script and static assets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Simple in-memory cache: url -> (timestamp, content, content_type)
CACHE = {}
CACHE_TTL = 60  # seconds

class ProxyHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. API proxy endpoints
        target_url = None
        if path == '/chart':
            ticker = query.get('ticker', ['SOXL'])[0].upper()
            range_val = query.get('range', ['1y'])[0]
            target_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_val}"
        elif path == '/vix':
            target_url = "https://query2.finance.yahoo.com/v8/finance/chart/^VIX?interval=1d&range=5d"

        if target_url:
            self._handle_proxy_request(target_url)
            return

        # 2. Serve static files (SOXL2.html, index.html, etc.)
        self._handle_static_file(path)

    def _handle_proxy_request(self, target_url):
        now = time.time()
        if target_url in CACHE:
            cached_time, cached_content, cached_type = CACHE[target_url]
            if now - cached_time < CACHE_TTL:
                self.send_response(200)
                self.send_header('Content-Type', cached_type)
                self.send_header('X-Cache-Status', 'HIT')
                self.end_headers()
                self.wfile.write(cached_content)
                return

        context = ssl._create_unverified_context()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://finance.yahoo.com/'
        }
        req = urllib.request.Request(target_url, headers=headers)
        try:
            with urllib.request.urlopen(req, context=context, timeout=8) as response:
                content = response.read()
                content_type = response.headers.get('Content-Type', 'application/json')
                CACHE[target_url] = (now, content, content_type)
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('X-Cache-Status', 'MISS')
                self.end_headers()
                self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error fetching data: {e}".encode('utf-8'))

    def _handle_static_file(self, path):
        if path == '/' or path == '':
            file_name = 'SOXL2.html'
        else:
            file_name = path.lstrip('/')

        file_path = os.path.join(BASE_DIR, file_name)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'text/html' if file_path.endswith('.html') else 'application/octet-stream'
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mime_type)
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error reading file: {e}".encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def log_message(self, format, *args):
        # Concise logging
        sys.stdout.write(f"[{self.log_date_time_string()}] {args[0]}\n")

def run(port=8080):
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, ProxyHandler)
    print(f"=================================================")
    print(f" SOXL Dashboard Server Running")
    print(f" Local URL: http://localhost:{port}/")
    print(f" Proxy APIs: http://localhost:{port}/chart, /vix")
    print(f"=================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\nServer stopped.")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run(port)

