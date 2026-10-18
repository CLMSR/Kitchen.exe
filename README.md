# Kitchen.exe

Kitchen.exe is a local-first recipe discovery and RSS/Atom reader. The current refactor preserves the existing UI language and storage keys while making storage access, recipe matching, feed refresh, and PWA caching more defensive.

## Run locally (recommended)

**Do not double-click `index.html`**: `file://` gives the page an opaque `null` origin, which blocks feed requests and prevents service-worker registration. If an older Kitchen.exe server is already running, stop it with Ctrl+C in its Terminal window before starting the updated copy. Keep your old folder until you have checked your data.

On macOS, double-click `start.command`. It starts a loopback-only local server and opens Kitchen.exe at `http://127.0.0.1:8765`. Keep the Terminal window open while using the app; press Ctrl+C in that window to stop it. If macOS blocks the script, right-click `start.command` → Open. Python 3 is required.

This local server also provides a same-origin bridge for RSSHub TikTok feeds, avoiding browser CORS restrictions and public CORS proxies for those requests. It tries the configured public RSSHub instances from the server side. It cannot guarantee a feed if TikTok or every RSSHub instance is unavailable.

For ordinary static hosting, the app can still be served over HTTP/HTTPS, but the local RSSHub bridge is only available when using `start.command`.

## Architecture

- `index.html` — current interface and application orchestration. The existing visual style and workflows are retained.
- `recipe-core.js` — shared ingredient normalization, URL canonicalization, date validation, and recipe normalization primitives.
- `storage-core.js` — defensive, backward-compatible localStorage adapter.
- `sw.js` — versioned app-shell cache. External feeds, proxies, and APIs are deliberately not cached by the service worker.
- `manifest.json` — PWA metadata and existing icon paths.
- `tests/core.test.cjs` — unit tests for shared core primitives.

## Search behavior

- TheMealDB recipes are hydrated with ingredient lists before scoring (up to 60 unique meals per search, with bounded concurrency).
- Results are deduplicated by canonical URL and ranked by ingredient matches, data completeness, and text relevance.
- The “All selected ingredients” filter only shows results whose available ingredient list or searchable text matches every selected ingredient. For social posts, matching is based on the visible title/excerpt, not a guarantee that the full recipe contains those ingredients.
- TikTok opens its public search page. Instagram and Substack shortcuts use public web search queries. These are clearly labeled as external discovery links, not indexed in-app social results; actual search coverage is controlled by those platforms.

## Feed behavior

- Feed refresh runs with a maximum of three concurrent feed workers.
- A failed update does not discard the last successfully fetched posts for that feed.
- Invalid dates are normalized to empty values rather than throwing during parsing.
- Feed/article URLs and image URLs are restricted to HTTP(S) before being rendered.
- Proxy availability is external and cannot be guaranteed by this app.

## Tests

Run the core unit tests with Node.js 18 or newer:

```bash
node --test tests/core.test.cjs
python tests/server.test.py
```

A static syntax/asset check should also be run after changes. Browser-based end-to-end testing is recommended in a normal local browser because this execution environment may restrict local browser navigation and external network requests.

## TikTok account feeds (RSSHub, no TikTok API or AI)

1. Open **Feeds → Add TikTok account**.
2. Paste a public profile URL (`https://www.tiktok.com/@creator`) or a handle (`@creator`).
3. Kitchen.exe generates the RSSHub TikTok route automatically and tries several public RSSHub instances if the first one fails. No RSS.app account is required.
4. If you already have an RSS URL from another provider, open **Advanced: paste another RSS URL (optional)** and paste it there.
5. Posts use the existing RSS parser, refresh, cards, search, read-state, and favorites flows.

This uses public RSSHub instances, not a TikTok API or AI. When launched with `start.command`, TikTok RSS requests pass through a small loopback-only Python bridge so browser CORS rules and unreliable public CORS proxies do not block the request. The bridge tries several public RSSHub instances server-side. The TikTok route is marked as anti-crawler and can still fail if TikTok changes its public pages or blocks every instance. Public instance availability cannot be guaranteed; an externally supplied RSS URL remains available as a fallback. It does not require signing into RSS.app. The feed usually provides a thumbnail and a link to the original TikTok post; playback remains on TikTok.

TikTok source metadata is included when exporting/importing the feed list. Existing RSS/Atom feeds continue to work as before.

## Cross-device synchronization options

The app remains local-first in this build. `localStorage` is specific to each browser/device, so simply installing the PWA on another device does not synchronize data. Options:

- **Manual JSON backup (free, no account/backend):** export/import feeds; a full-data backup/restore workflow can be added separately. Not automatic and does not merge changes.
- **Firebase Authentication + Cloud Firestore (free Spark quota):** recommended for an automatic sync version of this static PWA. It requires a Firebase project, authentication, per-user Firestore security rules, and a small sync adapter. Stay within the Spark quotas and do not enable billing unless you explicitly choose to.
- **Supabase Auth + PostgreSQL (free plan):** good if a relational data model and SQL queries are preferred. Requires a project, Row Level Security policies and a sync adapter; review free-plan inactivity and quota policies.
- **Self-hosted sync server:** most control, but not the simplest free option because hosting, security, backups and maintenance become your responsibility.

No cloud-sync provider is configured in this ZIP; credentials and user identity must be configured before cloud sync can be safely enabled. A sync implementation should synchronize feeds, saved recipes, read states, categories, theme and preferences per user, with conflict handling and a local offline cache. Avoid uploading credentials or sharing one global database key among users.


## Recipe discovery and unified feed updates (2026-10)

- Explore supports ingredient match modes: any selected ingredient (partial/optional match) or all selected ingredients (required match).
- Added excluded-ingredient, maximum-known-time, and dish-type filters. Time/type/exclusion filters use available metadata; social posts without structured recipe data cannot be fully verified.
- Search ranking remains deterministic and explainable: ingredient match ratio, structured ingredient-list availability, recipe instructions, image, and text relevance. No AI is used.
- Unified feed now filters by source/platform and creator/source name, supports relevance ordering against the keyword filter, and lets users hide or restore individual posts. Dismissed-post IDs persist in `localStorage` under `kitchenExeDismissed`.
- Recipe details support personal notes and comma-separated tags, stored alongside saved items. Structured recipe metadata is preserved where available.
- Fixed a Reddit result-link bug where the link sanitizer referenced an undefined `feedUrl`, which caused Reddit search parsing to fail.
- Duration parsing is shared in `recipe-core.js` and covered by unit tests.

### Validation

Run `node --test tests/core.test.cjs` from this folder. Browser integration still needs to be tested with real RSS sources and network conditions.

## Global keyword search (Discover tab)

- The **Discover** tab accepts free-text queries such as `healthy tiramisu`, `tiramisú saludable`, or `high-protein breakfast`. The query is sent as written; the app does not translate or force English.
- When launched with `start.command`, the local Python server queries public web search result pages for general websites and domain-specific results from YouTube, TikTok, Instagram and Reddit, then deduplicates URLs into a unified card grid. Search engine HTML is not a stable API; availability, ranking, thumbnails and social coverage depend on the public search engine and platform indexing.
- The first results without thumbnails are checked in the background for public Open Graph / JSON-LD image metadata (up to eight per search). If the local search route is unavailable or no results can be parsed, Discover offers direct search links for each source instead of pretending it has in-app results.
- Opening **Recipe details** asks the local server to read public page metadata and JSON-LD `Recipe` structured data. Ingredients, instructions, author, timings, yield and nutrition are displayed only when the source publishes them. The app does not invent cooking steps or nutrition estimates. Some social sites block automated page access, so the original post may need to be opened directly.
- Recipe metadata extraction is limited to public HTTP(S) pages. The local server binds to `127.0.0.1` only and should not be exposed to the public internet.

## Visual identity

The app icon has been replaced with a simple retro cooking-pot-and-sprout mark in cream, forest green and terracotta. PWA cache version is updated so browsers can load the new icon and Discover panel.


### Search fails with `CERTIFICATE_VERIFY_FAILED` on macOS

The local server keeps TLS certificate verification enabled. If all search providers fail with `unable to get local issuer certificate`, repair the CA certificates for the Python installation used by `start.command`. For Python.org installers, run the matching `Install Certificates.command` in `/Applications/Python 3.x/`. If using Homebrew Python, update/reinstall Python and ensure the system CA store is available. Restart `start.command` afterward. Do not disable SSL verification. The server also uses `certifi` automatically when that package is installed.
