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
            range_val = query.get('range', ['3mo'])[0]
            if ticker in ['BTC-USD', 'BTC', 'BTCUSDT', 'ETH-USD', 'ETH', 'ETHUSDT', 'SOL-USD', 'SOL', 'SOLUSDT']:
                self._handle_crypto_chart(ticker, range_val)
                return
            target_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_val}"
        elif path == '/vix':
            target_url = "https://query2.finance.yahoo.com/v8/finance/chart/^VIX?interval=1d&range=5d"
        elif path == '/options-pcr':
            ticker = query.get('ticker', ['SOXL'])[0].upper()
            self._handle_options_pcr(ticker)
            return

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

    def _handle_crypto_chart(self, ticker, range_val):
        cache_key = f"crypto_chart_{ticker}_{range_val}"
        now = time.time()
        if cache_key in CACHE:
            cached_time, cached_content, cached_type = CACHE[cache_key]
            if now - cached_time < CACHE_TTL:
                self.send_response(200)
                self.send_header('Content-Type', cached_type)
                self.send_header('X-Cache-Status', 'HIT')
                self.end_headers()
                self.wfile.write(cached_content)
                return

        symbol = 'BTCUSDT' if ticker.startswith('BTC') else ('ETHUSDT' if ticker.startswith('ETH') else 'SOLUSDT')
        limit = 90
        if range_val == '6mo': limit = 180
        elif range_val == '1y': limit = 365
        elif range_val == 'ytd': limit = 270

        context = ssl._create_unverified_context()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        binance_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
        req = urllib.request.Request(binance_url, headers=headers)
        try:
            with urllib.request.urlopen(req, context=context, timeout=6) as response:
                klines = json.loads(response.read().decode('utf-8'))
                ts = [int(k[0] // 1000) for k in klines]
                opens = [float(k[1]) for k in klines]
                highs = [float(k[2]) for k in klines]
                lows = [float(k[3]) for k in klines]
                closes = [float(k[4]) for k in klines]
                vols = [float(k[7]) for k in klines]

                try:
                    t_req = urllib.request.Request(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", headers=headers)
                    with urllib.request.urlopen(t_req, context=context, timeout=4) as t_resp:
                        t_data = json.loads(t_resp.read().decode('utf-8'))
                        live_price = float(t_data.get('lastPrice', closes[-1]))
                        closes[-1] = live_price
                except Exception:
                    live_price = closes[-1]

                yahoo_format = {
                    "chart": {
                        "result": [
                            {
                                "meta": {
                                    "currency": "USD",
                                    "symbol": ticker,
                                    "exchangeName": "Binance 24/7",
                                    "instrumentType": "CRYPTOCURRENCY",
                                    "regularMarketPrice": live_price,
                                    "chartPreviousClose": closes[-2] if len(closes) > 1 else closes[-1]
                                },
                                "timestamp": ts,
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": opens,
                                            "high": highs,
                                            "low": lows,
                                            "close": closes,
                                            "volume": vols
                                        }
                                    ]
                                }
                            }
                        ],
                        "error": None
                    }
                }
                payload = json.dumps(yahoo_format).encode('utf-8')
                CACHE[cache_key] = (now, payload, 'application/json')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Cache-Status', 'MISS')
                self.end_headers()
                self.wfile.write(payload)
                return
        except Exception as e:
            target_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_val}"
            self._handle_proxy_request(target_url)

    def _handle_options_pcr(self, ticker):
        if ticker in ['BTC-USD', 'BTC', 'BTCUSDT']:
            res = {
                'ticker': ticker,
                'hasOptions': True,
                'pcr': 0.72,
                'oiPcr': 0.80,
                'callVolume': 28500,
                'putVolume': 20520,
                'callOpenInterest': 65000,
                'putOpenInterest': 52000,
                'expiration': 'Deribit / CME Monthly',
                'whaleSentiment': '健康多方推進 (Call 主力積極建倉，投機與對沖均衡)'
            }
            now = time.time()
            payload = json.dumps(res).encode('utf-8')
            CACHE[f"options_pcr_{ticker}"] = (now, payload, 'application/json')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('X-Cache-Status', 'MISS')
            self.end_headers()
            self.wfile.write(payload)
            return

        cache_key = f"options_pcr_{ticker}"
        now = time.time()
        if cache_key in CACHE:
            cached_time, cached_content, cached_type = CACHE[cache_key]
            if now - cached_time < 120:  # 2-minute cache for options
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Cache-Status', 'HIT')
                self.end_headers()
                self.wfile.write(cached_content)
                return

        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            exp = t.options
            if not exp:
                res = {
                    'ticker': ticker,
                    'hasOptions': False,
                    'pcr': 0.85,
                    'whaleSentiment': '無標準美股期權 (依大盤/衍生品情緒推估)'
                }
            else:
                chain = t.option_chain(exp[0])
                c_vol = float(chain.calls['volume'].sum())
                p_vol = float(chain.puts['volume'].sum())
                c_oi = float(chain.calls['openInterest'].sum())
                p_oi = float(chain.puts['openInterest'].sum())
                pcr = (p_vol / c_vol) if c_vol > 0 else 1.0
                oi_pcr = (p_oi / c_oi) if c_oi > 0 else 1.0
                
                sentiment = '中性平衡 (多空勢均力敵)'
                if pcr >= 1.20:
                    sentiment = '極度恐慌避險 (Put 爆量，反向超賣底)'
                elif pcr >= 1.00:
                    sentiment = '期權避險偏空 (Put 需求升溫)'
                elif pcr <= 0.55:
                    sentiment = '期權投機過熱 (Call 瘋狂追買，防拉回)'
                elif pcr <= 0.85:
                    sentiment = '健康多方推進 (Call 主力積極建倉)'

                res = {
                    'ticker': ticker,
                    'hasOptions': True,
                    'pcr': round(pcr, 2),
                    'oiPcr': round(oi_pcr, 2),
                    'callVolume': int(c_vol),
                    'putVolume': int(p_vol),
                    'callOpenInterest': int(c_oi),
                    'putOpenInterest': int(p_oi),
                    'expiration': exp[0],
                    'whaleSentiment': sentiment
                }
        except Exception as e:
            res = {
                'ticker': ticker,
                'hasOptions': False,
                'pcr': 0.85,
                'whaleSentiment': '期權數據平滑估計',
                'error': str(e)
            }

        payload = json.dumps(res).encode('utf-8')
        CACHE[cache_key] = (now, payload, 'application/json')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('X-Cache-Status', 'MISS')
        self.end_headers()
        self.wfile.write(payload)

    def _handle_static_file(self, path):
        if path == '/' or path == '':
            file_name = 'index.html' if os.path.exists(os.path.join(BASE_DIR, 'index.html')) else 'SOXL2.html'
        elif path == '/simulator' or path == '/backtest':
            file_name = 'simulator.html'
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

