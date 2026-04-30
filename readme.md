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

### Sitemap PDP Discovery POC
The sandbox API now includes a sitemap discovery endpoint that traverses a
public sitemap entrypoint and returns candidate PDP links.

Example request body:
```json
{
  "retailer_name": "ikea"
}
```

Ad hoc request body:
```json
{
  "sitemap_url": "https://www.example.com/sitemap.xml",
  "include_patterns": ["/product/", "/p/"],
  "exclude_patterns": ["/blog/", "/category/"],
  "max_depth": 3,
  "max_sitemaps": 50
}
```

Route:
```bash
POST /sandbox/discover/pdp-links
```

Dump-to-file route:
```bash
POST /sandbox/discover/pdp-links/dump
```

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
SNOWFLAKE_SCHEMA_NAME=PUBLIC
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
```

The repo includes a matching [`.env.example`](/Users/pototo/codebase/wordome/.env.example) template.
Note: Provide actual credential values locally in `.env` file (avoid comitting this actual file)

### Snowflake SQL - Bootstrap
Run this after first-time credential setup, or when the pre-migration snapshot table shape changes:

```bash
> make bootstrap-snowflake
```

This bootstrap flow is designed to be idempotent:
- it creates the configured database and schema if missing
- it creates the `review_scrapes` table if missing
- it applies the current one-time legacy snapshot column alignment if needed

### Draft Sitemap Crawl Schema
The repo also includes draft ORM models for a future sitemap crawl persistence
shape in [sitemap_crawl_orm.py](/Users/pototo/codebase/wordome/src/wordome/infrastructure/database/sitemap_crawl_orm.py).
They are intentionally not wired into active writes yet. The bootstrap code path
has been prepared to create the draft tables when `make bootstrap-snowflake` is
eventually run.
