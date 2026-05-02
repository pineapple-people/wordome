## Anaconda (Miniconda)

### First Time Setup
```
# Create environment from configuration file
> conda env create -f environment.yaml

# Verify environment was created
> conda env list
```

### Usage
```
# Activate environment
> conda activate wordome_env

# Deactivate environment
> conda deactivate
```

### Updating environment (to match config file)
```
# Update environment with any changes to environment.yaml
> conda env update -f environment.yaml

# Update and remove packages not in the file (clean)
> conda env update -f environment.yaml --prune
```

### Installing Packages
```
# Install via conda-forge channel (Conda's canonical source)
# Note: Try through Conda first, fallback to pip (Conda ensures compatible dependencies)
conda install -c conda-forge beautifulsoup4
```

## Wordome Application

### Install (Development Mode) 
```
# Install the package in development mode
> pip install -e .

# Conversely, this uninstall command can be useful for troubleshooting
> pip uninstall wordome -y
```

### Running the app
Command shape:
```bash
> wordome [--mode {api,demo}] [--trace [live|buffered]]
```

Optional args:
```bash
# Switch modes (`api` is the default)
> --mode demo

# Set scrape trace mode
# If no value is given, `--trace` defaults to `live`
> --trace
> --trace live
> --trace buffered

# Show CLI help and examples
> --help
```

Examples:
```
# API service (default mode)
# Note: this alias is defined within pyproject.toml
> wordome

# Demo mode (executes a fixed flow that showcases basic functionality)
> wordome --mode demo

# API service with buffered scrape trace output
> wordome --trace buffered

# Show CLI help and examples
> wordome --help
```

### API Usage
Run the API locally:

```bash
> wordome
```

Then use the built-in API docs as the source of truth for request and response
schemas:

```text
Swagger UI: http://127.0.0.1:8000/docs
ReDoc:      http://127.0.0.1:8000/redoc
```

The interactive docs are generated from the FastAPI route and model
definitions, so they stay current as the code evolves.

### Happy Path Example
Standard crawl-to-review flow:

```bash
# 1. Start the API
> wordome

# 2. Trigger a sitemap crawl using the retailer's default configured sitemap
> curl -X POST http://127.0.0.1:8000/sitemap-crawls \
    -H "Content-Type: application/json" \
    -d '{"retailer_name":"ikea"}'

# 2a. The kickoff returns 202 Accepted with a crawl_run_id and running status
# 2b. Retrieve sitemap crawl status by crawl_run_id while the background task runs
> curl http://127.0.0.1:8000/sitemap-crawls/<crawl_run_id>

# 2c. Wait until the crawl status reaches `completed` or `completed_with_errors`
# 3. Then trigger review scraping from the crawl-derived PDP URLs
> curl -X POST http://127.0.0.1:8000/review-scrapes/crawl \
    -H "Content-Type: application/json" \
    -d '{"retailer_name":"ikea","limit":10}'
```

Optional ad-hoc single PDP processing:

```bash
> curl -X POST http://127.0.0.1:8000/review-scrapes/single \
    -H "Content-Type: application/json" \
    -d '{"retailer_name":"ikea","product_url":"https://www.ikea.com/us/en/p/slattum-upholstered-bed-frame-vissle-dark-gray-40571253/","persist_result":true}'
```

Queue inspection:

```bash
# View queue items, optionally filtered by retailer_name and queue_status
> curl "http://127.0.0.1:8000/review-scrape-queue?retailer_name=ikea&queue_status=unclaimed&limit=10"

# View aggregate queue counts, optionally filtered by retailer_name
> curl "http://127.0.0.1:8000/review-scrape-queue/summary?retailer_name=ikea"
```

Sandbox routes remain available for POC and debugging workflows under
`/sandbox/...`, but the generated Swagger docs should be the primary reference
for the public API surface.

### Pipeline Data Model
`Grain` means what a single row in the table represents.

#### Sitemap Crawl Stage

| Table | Grain | Purpose |
|---|---|---|
| `sitemap_crawl_runs` | 1 row per sitemap crawl execution | Track sitemap crawl job lifecycle, counts, and status |
| `sitemap_crawl_records` | 1 row per retailer + observed/discovered URL | Persist crawl-discovered URL state and classification |

#### Review Scrape Handoff

| Table | Grain | Purpose |
|---|---|---|
| `review_scrape_queue` | 1 row per retailer + PDP URL in the sitemap-to-review handoff layer | Queue-state layer between sitemap discovery and review scraping |

Lifecycle:
- inserted by the sitemap crawl stage when a PDP URL becomes eligible for review scraping
- moved to `claimed` while a review scrape run is actively processing it
- returned to `unclaimed` on failure/retry with the latest run/error context preserved
- moved to `completed` on successful review scrape for later cleanup/reconciliation

#### Review Scrape Stage

| Table | Grain | Purpose |
|---|---|---|
| `review_scrape_pipeline_runs` | 1 row per review scrape execution | Track review scrape job lifecycle, counts, and trigger type |
| `review_scrapes` | 1 row per PDP scrape snapshot/event | Historical record of raw review scrape output |
| `review_scrape_records` | 1 row per deduped review entry | Latest/current persisted review-entry state |

## Utility

### Ruff (code quality tool)
```
# Run this as code changes are made to auto-format and lint code
# Note: fails if corrections cannot be applied automatically
> make ruff
```

### Smoke Check
```bash
# Run a lightweight smoke check without touching Snowflake:
# verifies key module imports, ORM table registration, and app wiring.
> make smoke-check
```

## Other Notes

### VS Code - Suggested configs
```
# settings.json
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

### Snowflake SQL - Credentials
This app integrates with Snowflake SQL as its persistence layer and the credentials are read from a root `.env` file. The app expects these keys:

```env
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_SCHEMA_NAME=...
SNOWFLAKE_WAREHOUSE=...
```

The repo includes a matching [`.env.example`](/Users/pototo/codebase/wordome/.env.example) template.
Note: Provide actual credential values locally in `.env` file (avoid comitting this actual file)

### Snowflake SQL - Bootstrap
Run this after first-time credential setup:

```bash
> make bootstrap-snowflake
```

This bootstrap flow is designed to be idempotent:
- it creates the configured database and schema if missing
- it creates the `review_scrape_queue` table if missing
- it creates the `review_scrape_pipeline_runs` table if missing
- it creates the `review_scrapes` table if missing
- it creates the `review_scrape_records` current-state table if missing
- it creates the `sitemap_crawl_runs` table if missing
- it creates the `sitemap_crawl_records` table if missing
