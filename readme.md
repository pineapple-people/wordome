## Wordome

Wordome collects product reviews from retailer websites. It finds product
pages, collects reviews from those pages, and saves the results for downstream
use, including ML processing of review content.

It is currently used through the API, with IKEA covered as the sample retailer
integration for MVP purposes.

## Overview

Use Wordome when you want to:
- start from a retailer site instead of manually collecting product links
- separate page discovery from review collection
- keep both run history and cleaned-up review data

## End-To-End Flow

```text
Retailer site
    ->
Find product pages
    ->
Prepare pages for review collection
    ->
Collect reviews
    ->
Save results for reuse
```

In short, Wordome finds product pages, collects reviews from them, and stores
the results for reuse. Under the hood, it uses retailer sitemaps and Snowflake.

## Usage Modes And CLI Options

Command shape:

```bash
wordome [--mode {api,demo}] [--trace [live|buffered]]
```

Examples:

```bash
# API service (default)
wordome

# API service with buffered scrape trace output
wordome --trace buffered

# Demo mode
wordome --mode demo

# CLI help
wordome --help
```

`api` is the default mode. `--trace` defaults to `live`. `demo` runs a fixed
fetching-and-processing flow, not the full sitemap-to-review pipeline.

For API usage, start the app with `wordome`, then open:

```text
Swagger UI: http://127.0.0.1:8000/docs
ReDoc:      http://127.0.0.1:8000/redoc
```

Use Swagger UI or ReDoc as the source of truth for:
- available endpoints
- request and response schemas
- example payloads
- trying requests locally from the browser

### Typical Workflow

1. Start the API with `wordome`.
2. Call `POST /sitemap-crawls` for a retailer such as `ikea`.
3. Wait until the crawl status becomes `completed` or `completed_with_errors`.
4. Call `POST /review-scrapes/crawl` to process queued PDP URLs.
5. Inspect queue health and persisted data in Snowflake.

### Single-PDP Ad Hoc Usage

Use this to test review scraping without running the full sitemap flow.

```bash
curl -X POST http://127.0.0.1:8000/review-scrapes/single \
  -H "Content-Type: application/json" \
  -d '{"retailer_name":"ikea","product_url":"https://www.ikea.com/us/en/p/slattum-upholstered-bed-frame-vissle-dark-gray-40571253/","persist_result":true}'
```

### Queue Inspection

```bash
curl "http://127.0.0.1:8000/review-scrape-queue?retailer_name=ikea&queue_status=unclaimed&limit=10"
curl "http://127.0.0.1:8000/review-scrape-queue/summary?retailer_name=ikea"
```

Sandbox routes under `/sandbox/...` still exist for experimentation and POC
workflows, but the generated API docs should be treated as the main public
surface.

## Pipeline Data Model

`Grain` means what a single row in the table represents.

### Sitemap Crawl Stage

| Table | Grain | Purpose |
|---|---|---|
| `sitemap_crawl_runs` | 1 row per sitemap crawl execution | Track sitemap crawl job lifecycle, counts, and status |
| `sitemap_crawl_records` | 1 row per retailer + observed/discovered URL | Persist crawl-discovered URL state and classification |

### Review Scrape Handoff

| Table | Grain | Purpose |
|---|---|---|
| `review_scrape_queue` | 1 row per retailer + PDP URL in the sitemap-to-review handoff layer | Queue-state layer between sitemap discovery and review scraping |

Queue lifecycle:
- inserted by the sitemap crawl stage when a PDP URL becomes eligible for review scraping
- moved to `claimed` while a review scrape run is actively processing it
- returned to `unclaimed` on failure or retry with the latest run and error context preserved
- moved to `completed` on successful review scrape for later cleanup or reconciliation

### Review Scrape Stage

| Table | Grain | Purpose |
|---|---|---|
| `review_scrape_pipeline_runs` | 1 row per review scrape execution | Track review scrape job lifecycle, counts, and trigger type |
| `review_scrapes` | 1 row per PDP scrape snapshot/event | Historical record of raw review scrape output |
| `review_scrape_records` | 1 row per deduped review entry | Latest/current persisted review-entry state |

## Quickstart And Setup

If you just want to prove the app works locally, use this path.

### 1. Create The Environment

```bash
conda env create -f environment.yaml
conda activate wordome_env
pip install -e .
```

### 2. Configure Snowflake Credentials

Create a root `.env` file from [`.env.example`](/Users/pototo/codebase/wordome/.env.example)
with:

```env
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_SCHEMA_NAME=...
SNOWFLAKE_WAREHOUSE=...
```

### 3. Bootstrap Database Objects

```bash
make bootstrap-snowflake
```

### 4. Start The API

```bash
wordome
```

### 5. Run The Happy Path

Kick off sitemap discovery:

```bash
curl -X POST http://127.0.0.1:8000/sitemap-crawls \
  -H "Content-Type: application/json" \
  -d '{"retailer_name":"ikea"}'
```

Poll the returned `crawl_run_id` until the run finishes:

```bash
curl http://127.0.0.1:8000/sitemap-crawls/<crawl_run_id>
```

Then scrape reviews from the crawl-derived queue:

```bash
curl -X POST http://127.0.0.1:8000/review-scrapes/crawl \
  -H "Content-Type: application/json" \
  -d '{"retailer_name":"ikea","limit":10}'
```

### Setup Details

#### Conda Environment

Create the environment:

```bash
conda env create -f environment.yaml
```

Activate and deactivate:

```bash
conda activate wordome_env
conda deactivate
```

Update the environment to match `environment.yaml`:

```bash
conda env update -f environment.yaml
conda env update -f environment.yaml --prune
```

#### Installing Packages

Prefer Conda first, then fall back to `pip` only if needed:

```bash
conda install -c conda-forge beautifulsoup4
```

#### Development Install

```bash
pip install -e .
pip uninstall wordome -y
```

#### Snowflake Bootstrap Notes

The bootstrap flow is designed to be idempotent. It creates the configured
database, schema, and these tables if they do not already exist:
- `review_scrape_queue`
- `review_scrape_pipeline_runs`
- `review_scrapes`
- `review_scrape_records`
- `sitemap_crawl_runs`
- `sitemap_crawl_records`

### Developer Utilities

#### Smoke Check

Run a lightweight verification without touching Snowflake:

```bash
make smoke-check
```

This checks:
- key module imports
- ORM table registration
- app wiring

#### Ruff

Format and lint the codebase:

```bash
make ruff
```

Check formatting and lint without modifying files:

```bash
make ruff-check
```

## Other Notes

### Suggested VS Code Settings

```json
{
  "python-envs.defaultEnvManager": "ms-python.python:conda",
  "python-envs.defaultPackageManager": "ms-python.python:conda",
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/.ruff_cache": true
  },
  "files.autoSave": "onFocusChange"
}
```
