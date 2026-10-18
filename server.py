#!/usr/bin/env python3
"""Loopback-only local server, RSSHub TikTok bridge, public search and recipe metadata."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode, urljoin
from urllib.request import Request, urlopen, HTTPRedirectHandler, HTTPSHandler, build_opener
from urllib.error import HTTPError, URLError
from pathlib import Path
from html.parser import HTMLParser
import html
import json
import re
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import webbrowser
import ssl
import os


def make_ssl_context():
    """Use verified TLS with a usable CA bundle; never disable certificate checks."""
    # Prefer an explicitly configured CA bundle, then certifi when installed.
    candidates = []
    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            candidates.append(value)
    try:
        import certifi  # type: ignore
        candidates.append(certifi.where())
    except Exception:
        pass
    for bundle in candidates:
        try:
            return ssl.create_default_context(cafile=bundle)
        except Exception:
            continue
    # Retain the platform trust store as a secure fallback.
    return ssl.create_default_context()


_SSL_CONTEXT = make_ssl_context()

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
RSSHUB_HOSTS = [
    "rsshub.app",
    "rsshub.rssforever.com",
    "hub.slarker.me",
    "rsshub.pseudoyu.com",
]


def public_http_url(raw_url):
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal")):
        return None
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses:
            return None
        if any(not ipaddress.ip_address(addr[4][0]).is_global for addr in addresses):
            return None
    except (OSError, ValueError):
        return None
    return parsed


class SafePublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if public_http_url(newurl) is None:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class KitchenHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/__kitchen/tiktok-feed":
            self.handle_tiktok_feed(params.get("url", [""])[0])
            return
        if parsed.path == "/__kitchen/search":
            self.handle_search(params.get("q", [""])[0], params.get("sources", ["all"])[0])
            return
        if parsed.path == "/__kitchen/recipe":
            self.handle_recipe(params.get("url", [""])[0])
            return
        super().do_GET()

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _safe_public_url(self, raw_url):
        return public_http_url(raw_url)

    class _SearchParser(HTMLParser):
        """Tolerant parser for DuckDuckGo HTML/Lite, Google and Bing result markup."""
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.results = []
            self._anchors = []
            self._active_anchor = None
            self._blocks = []
            self._active_block = None
            self._capture = None
            self._capture_depth = 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            classes = set(a.get("class", "").split())
            if tag in ("div", "li", "article") and classes.intersection({"result", "results_links", "MjjYud", "g", "b_algo", "web-result"}):
                self._active_block = {"title": "", "url": "", "excerpt": "", "image": "", "depth": 1}
            elif self._active_block and tag in ("div", "li", "article", "p", "h2", "h3", "td"):
                self._active_block["depth"] += 1

            if tag == "a":
                href = a.get("href", "")
                parsed = urlparse(href)
                if href.startswith("//"):
                    href = "https:" + href
                    parsed = urlparse(href)
                if parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
                    href = parse_qs(parsed.query).get("uddg", [href])[0]
                elif parsed.hostname and parsed.hostname.endswith("google.com") and parsed.path == "/url":
                    href = parse_qs(parsed.query).get("q", parse_qs(parsed.query).get("url", [href]))[0]
                is_result_link = bool(classes.intersection({"result__a", "result-link", "b_title"})) or (self._active_block is not None and not self._active_block.get("url") and href.startswith("http"))
                if is_result_link and href.startswith("http"):
                    self._active_anchor = {"title": "", "url": href, "excerpt": "", "image": "", "classes": classes}
                    self._capture = "title"
                elif self._active_block and not self._active_block.get("url") and href.startswith("http"):
                    self._active_block["url"] = href
            if "result__snippet" in classes or "VwiC3b" in classes or "b_caption" in classes or "result-snippet" in classes:
                self._capture = "excerpt"
                self._capture_depth = self._active_block.get("depth", 0) if self._active_block else 0
            if tag == "img":
                src = a.get("src") or a.get("data-src") or ""
                target = self._active_anchor or self._active_block
                if target is not None and src.startswith("https://") and not target.get("image"):
                    target["image"] = src

        def handle_data(self, data):
            if self._active_anchor is not None and self._capture == "title":
                self._active_anchor["title"] += data
            elif self._capture == "excerpt":
                if self._active_block is not None:
                    self._active_block["excerpt"] += data
                elif self.results:
                    self.results[-1]["excerpt"] += data

        def handle_endtag(self, tag):
            if tag == "a" and self._active_anchor is not None:
                item = self._active_anchor
                item["title"] = re.sub(r"\s+", " ", item["title"]).strip()
                if item["url"] and item["title"]:
                    self.results.append({k: item.get(k, "") for k in ("title", "url", "excerpt", "image")})
                    if self._active_block is not None and not self._active_block.get("url"):
                        self._active_block["url"] = item["url"]
                        self._active_block["title"] = item["title"]
                self._active_anchor = None
                self._capture = None
            if tag in ("p", "div", "td") and self._capture == "excerpt":
                self._capture = None
            if self._active_block and tag in ("div", "li", "article", "p", "h2", "h3", "td"):
                self._active_block["depth"] -= 1
                if self._active_block["depth"] <= 0:
                    block = self._active_block
                    if block.get("url") and block.get("title"):
                        existing = next((x for x in self.results if x["url"] == block["url"]), None)
                        if existing is None:
                            self.results.append({k: block.get(k, "") for k in ("title", "url", "excerpt", "image")})
                        else:
                            if block.get("excerpt") and not existing.get("excerpt"):
                                existing["excerpt"] = re.sub(r"\s+", " ", block["excerpt"]).strip()
                            if block.get("image") and not existing.get("image"):
                                existing["image"] = block["image"]
                    self._active_block = None

    def _search_engine(self, query):
        engines = [
            "https://html.duckduckgo.com/html/?" + urlencode({"q": query}),
            "https://lite.duckduckgo.com/lite/?" + urlencode({"q": query}),
            "https://www.google.com/search?" + urlencode({"q": query, "udm": "14"}),
            "https://www.bing.com/search?" + urlencode({"q": query}),
        ]
        last_error = "No search results returned"
        for target in engines:
            request = Request(target, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.8,es;q=0.7",
            })
            try:
                with urlopen(request, timeout=8, context=_SSL_CONTEXT) as response:
                    page = response.read(2_500_000).decode("utf-8", "replace")
                parser = self._SearchParser()
                parser.feed(page)
                if parser.results:
                    cleaned = []
                    for item in parser.results:
                        url = html.unescape(item.get("url", "")).strip()
                        title = re.sub(r"\s+", " ", html.unescape(item.get("title", ""))).strip()
                        excerpt = re.sub(r"\s+", " ", html.unescape(item.get("excerpt", ""))).strip()
                        parsed = urlparse(url)
                        if parsed.scheme not in ("http", "https") or not parsed.hostname or not title:
                            continue
                        if parsed.hostname.endswith("duckduckgo.com") or parsed.hostname.endswith("google.com"):
                            continue
                        cleaned.append({"title": title[:300], "url": url, "excerpt": excerpt[:700], "image": item.get("image", "")})
                    if cleaned:
                        return cleaned, ""
                last_error = "Search engine returned no parseable results"
            except Exception as exc:
                last_error = type(exc).__name__ + (": " + str(exc)[:160] if str(exc) else "")
                if isinstance(exc, URLError) and "CERTIFICATE_VERIFY_FAILED" in str(exc):
                    last_error += " (Install/repair Python certificates on macOS; TLS verification remains enabled.)"
        return [], "All public search providers failed: " + last_error

    def handle_search(self, query, sources_raw):
        query = str(query or "").strip()[:220]
        if len(query) < 2:
            self.send_json(400, {"error": "Enter at least two characters.", "results": []})
            return
        source_keys = [x for x in str(sources_raw or "all").split(",") if x]
        allowed = {"web", "tiktok", "youtube", "instagram", "reddit"}
        if not source_keys or "all" in source_keys:
            source_keys = ["web", "tiktok", "youtube", "instagram", "reddit"]
        source_keys = [x for x in source_keys if x in allowed]
        domains = {
            "tiktok": "site:tiktok.com",
            "youtube": "site:youtube.com",
            "instagram": "site:instagram.com",
            "reddit": "site:reddit.com",
        }
        jobs = []
        if "web" in source_keys:
            jobs.append(("web", query))
        for key in source_keys:
            if key in domains:
                jobs.append((key, f'{query} {domains[key]}'))
        results, errors = [], []
        with ThreadPoolExecutor(max_workers=min(5, len(jobs) or 1)) as pool:
            futures = {pool.submit(self._search_engine, q): key for key, q in jobs}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    items, error = future.result()
                    if error:
                        errors.append({"source": key, "error": error})
                    for result_rank, item in enumerate(items[:12]):
                        item["_queryRank"] = source_keys.index(key) if key in source_keys else 99
                        item["_resultRank"] = result_rank
                        parsed = urlparse(item["url"])
                        host = (parsed.hostname or "").lower().removeprefix("www.")
                        source = key
                        if key == "web":
                            if "tiktok.com" in host: source = "tiktok"
                            elif "youtube.com" in host or "youtu.be" in host: source = "youtube"
                            elif "instagram.com" in host: source = "instagram"
                            elif "reddit.com" in host: source = "reddit"
                        item.update({"source": source, "sourceLabel": {"web":"Website / blog","tiktok":"TikTok","youtube":"YouTube","instagram":"Instagram","reddit":"Reddit"}.get(source, source.title()), "host": host, "id": item["url"]})
                        results.append(item)
                except Exception as exc:
                    errors.append({"source": key, "error": type(exc).__name__})
        deduped, seen = [], set()
        for item in results:
            key = item["url"].split("#", 1)[0].rstrip("/").lower()
            if key in seen: continue
            seen.add(key)
            if item["source"] == "web" and any(domain in item["host"] for domain in ("tiktok.com", "youtube.com", "youtu.be", "instagram.com", "reddit.com")):
                continue
            deduped.append(item)
        deduped = [item for item in deduped if item["source"] in source_keys]
        deduped.sort(key=lambda x: (source_keys.index(x["source"]) if x["source"] in source_keys else 99, x.get("_resultRank", 99)))
        for item in deduped:
            item.pop("_queryRank", None)
            item.pop("_resultRank", None)
        self.send_json(200, {"query": query, "results": deduped[:60], "errors": errors, "provider": "public web search"})

    def handle_recipe(self, supplied_url):
        parsed = self._safe_public_url(supplied_url)
        if not parsed:
            self.send_json(400, {"error": "Only public HTTP(S) recipe pages can be inspected."})
            return
        req = Request(parsed.geturl(), headers={
            "User-Agent": "Mozilla/5.0 (compatible; KitchenExe/3.0; +recipe-metadata-extractor)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        })
        try:
            with build_opener(HTTPSHandler(context=_SSL_CONTEXT), SafePublicRedirectHandler()).open(req, timeout=9) as response:
                final_url = response.geturl()
                final_parsed = self._safe_public_url(final_url)
                if not final_parsed:
                    self.send_json(400, {"error": "The page redirected to a non-public URL."})
                    return
                page = response.read(4_000_000).decode("utf-8", "replace")
            metas = {}
            for tag in re.findall(r"<meta\b[^>]*>", page, re.I):
                name = re.search(r"""(?:property|name)=["']([^"']+)["']""", tag, re.I)
                content = re.search(r"""content=["']([^"']*)["']""", tag, re.I)
                if name and content: metas[name.group(1).lower()] = html.unescape(content.group(1))
            title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
            title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""
            image = urljoin(final_url, metas.get("og:image") or metas.get("twitter:image") or "")
            description = metas.get("og:description") or metas.get("description") or metas.get("twitter:description") or ""
            recipe = None
            scripts = re.findall(r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""", page, re.I | re.S)
            def walk(obj):
                if isinstance(obj, list):
                    for child in obj:
                        found = walk(child)
                        if found: return found
                elif isinstance(obj, dict):
                    typ = obj.get("@type", [])
                    if isinstance(typ, str): typ = [typ]
                    if any(str(t).lower() == "recipe" for t in typ): return obj
                    for val in obj.values():
                        found = walk(val)
                        if found: return found
                return None
            for script in scripts:
                try:
                    obj = json.loads(html.unescape(script.strip()))
                    recipe = walk(obj)
                    if recipe: break
                except Exception:
                    continue
            def textval(v):
                if isinstance(v, (str, int, float)): return str(v)
                return ""
            details = {"title": title or metas.get("og:title", ""), "url": final_url, "image": image, "description": description, "foundRecipe": bool(recipe), "ingredients": [], "instructions": [], "nutrition": {}, "author": "", "prepTime": "", "cookTime": "", "totalTime": "", "yield": "", "category": "", "cuisine": ""}
            if recipe:
                details["title"] = textval(recipe.get("name")) or details["title"]
                details["description"] = textval(recipe.get("description")) or details["description"]
                image_val = recipe.get("image")
                if isinstance(image_val, list): image_val = next((x for x in image_val if isinstance(x, str)), image_val[0] if image_val else "")
                if isinstance(image_val, dict): image_val = image_val.get("url") or image_val.get("contentUrl") or ""
                details["image"] = urljoin(final_url, textval(image_val) or image) if (textval(image_val) or image) else ""
                raw_ingredients = recipe.get("recipeIngredient", []) or []
                if isinstance(raw_ingredients, str): raw_ingredients = [raw_ingredients]
                details["ingredients"] = [textval(x) for x in raw_ingredients if textval(x)]
                instructions = recipe.get("recipeInstructions", [])
                if isinstance(instructions, str): instructions = [instructions]
                flat = []
                for step in instructions if isinstance(instructions, list) else []:
                    if isinstance(step, str): flat.append(step.strip())
                    elif isinstance(step, dict):
                        if step.get("text"): flat.append(str(step["text"]).strip())
                        elif step.get("itemListElement"):
                            for sub in step["itemListElement"]:
                                if isinstance(sub, dict) and sub.get("text"): flat.append(str(sub["text"]).strip())
                details["instructions"] = [x for x in flat if x]
                for key, field in (("prepTime","prepTime"),("cookTime","cookTime"),("totalTime","totalTime"),("yield","recipeYield"),("category","recipeCategory"),("cuisine","recipeCuisine")):
                    value = recipe.get(field, "")
                    details[key] = ", ".join(map(str, value)) if isinstance(value, list) else textval(value)
                author = recipe.get("author", "")
                if isinstance(author, list): author = author[0] if author else ""
                details["author"] = textval(author.get("name") if isinstance(author, dict) else author)
                nutrition = recipe.get("nutrition", {})
                if isinstance(nutrition, dict):
                    for key in ("calories", "proteinContent", "carbohydrateContent", "fatContent", "fiberContent", "sugarContent", "sodiumContent"):
                        if nutrition.get(key): details["nutrition"][key] = textval(nutrition[key])
            self.send_json(200, details)
        except Exception as exc:
            self.send_json(502, {"error": "Could not read recipe metadata: " + type(exc).__name__})

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
                "User-Agent": "Mozilla/5.0 (compatible; KitchenExe/2.5; +local-feed-reader)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            })
            try:
                with urlopen(request, timeout=9, context=_SSL_CONTEXT) as response:
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
