# Kitchen.exe

Kitchen.exe is a local-first recipe discovery and RSS/Atom reader. The current refactor preserves the existing UI language and storage keys while making storage access, recipe matching, feed refresh, and PWA caching more defensive.

## Run locally

Serve this folder over HTTP (recommended for fetch, PWA and service-worker behavior):

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

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
```

A static syntax/asset check should also be run after changes. Browser-based end-to-end testing is recommended in a normal local browser because this execution environment may restrict local browser navigation and external network requests.

## TikTok account feeds (no TikTok API or AI)

1. Open **Feeds → Add TikTok account**.
2. Paste the public TikTok profile URL, such as `https://www.tiktok.com/@creator`.
3. Open the linked TikTok RSS generator, create a feed for that public profile, and copy the generated RSS URL.
4. Paste the RSS URL into Kitchen.exe and select **Add TikTok feed**.
5. Kitchen.exe stores the feed as a TikTok source and uses the existing RSS parser, refresh, card, search, read-state, and favorites flows.

This integration does not scrape TikTok directly and does not use the TikTok API or AI. RSS generation is provided by the external feed service; availability, refresh frequency, and free-tier limits depend on that provider. The RSS item normally contains a video thumbnail and a link to the original TikTok post, not the playable video itself. Public profiles only.

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
