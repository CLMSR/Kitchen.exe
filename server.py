#!/usr/bin/env python3
"""Local launcher for Kitchen.exe with a same-origin RSSHub TikTok bridge."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
RSSHUB_HOSTS = [
    "rsshub.app",
    "rsshub.rssforever.com",
    "hub.slarker.me",
    "rsshub.pseudoyu.com",
]

class KitchenHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/__kitchen/tiktok-feed":
            self.handle_tiktok_feed(parse_qs(parsed.query).get("url", [""])[0])
            return
        super().do_GET()

    def handle_tiktok_feed(self, supplied_url):
        try:
            parsed = urlparse(supplied_url)
            if parsed.scheme != "https" or parsed.hostname not in RSSHUB_HOSTS:
                self.send_error(400, "Only approved HTTPS RSSHub hosts are allowed")
                return
            if not parsed.path.startswith("/tiktok/user/") or len(parsed.path.split("/")) < 4:
                self.send_error(400, "Only RSSHub TikTok user feeds are supported")
                return
        except Exception:
            self.send_error(400, "Invalid feed URL")
            return

        # Try the requested RSSHub host first, then the other public instances.
        hosts = [parsed.hostname] + [host for host in RSSHUB_HOSTS if host != parsed.hostname]
        errors = []
        for host in hosts:
            target = parsed._replace(netloc=host).geturl()
            request = Request(target, headers={
                "User-Agent": "Mozilla/5.0 (compatible; KitchenExe/2.3; +local-feed-reader)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            })
            try:
                with urlopen(request, timeout=9) as response:
                    body = response.read(5_000_000)
                    if response.status == 200 and body:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    errors.append(f"{host}: HTTP {response.status}")
            except HTTPError as exc:
                errors.append(f"{host}: HTTP {exc.code}")
            except (URLError, TimeoutError, OSError) as exc:
                errors.append(f"{host}: {type(exc).__name__}")

        message = ("RSSHub TikTok feed unavailable. Tried: " + "; ".join(errors)).encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def log_message(self, fmt, *args):
        print("[Kitchen.exe] " + (fmt % args))

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), KitchenHandler)
    url = f"http://{HOST}:{PORT}/index.html"
    print(f"Kitchen.exe is running at {url}")
    print("Keep this window open while using the app. Press Ctrl+C to stop.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Kitchen.exe server...")
    finally:
        server.server_close()
