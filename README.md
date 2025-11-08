# Lead Intelligence Pipeline v0

Single-file lead discovery skeleton that enriches target firms with Playwright-backed scraping, Gemini analysis, and Google Sheets output.

## Overview

Find a domain. Pull public signals. Ask an LLM to score ICP fit. Append a normalized row to a Google Sheet.

## Features

- Requests + BeautifulSoup for fast static scrape.  
- Automatic Playwright fallback with cookie persistence.  
- Headful login flow to capture cookies once, then headless runs.  
- Strict Pydantic schema for deterministic JSON from the model.  
- Google Sheets append-only writer with duplicate domain guard.  
- Minimal logging with clear failure paths.

## Stack

- Python 3.10+  
- Playwright (Chromium)  
- Requests, BeautifulSoup4  
- Pydantic  
- Google Gemini via `google-genai`  
- gspread + Service Account auth

## Project Layout

```
lead_pipeline_v0.py
service_account.json            # your GCP service account key (not committed)
pw_storage_state.json           # Playwright cookies/localStorage
.env                            # environment variables
```

## Requirements

```
pip install playwright gspread oauth2client beautifulsoup4 requests pydantic python-dotenv google-genai
playwright install
```

Chrome is not required. Playwright installs its own Chromium.

## Configuration

Create `.env` in the repo root:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Constants inside the script:

```python
SERVICE_ACCOUNT_FILE = "service_account.json"
SHEET_NAME = "Lead Intelligence"
COMPANIES_SHEET_NAME = "companies"
PLAYWRIGHT_STATE_FILE = "pw_storage_state.json"
SHEET_SLEEP = 1.2
HTTP_TIMEOUT = 15
LOG_LEVEL = logging.INFO
```

Adjust as needed.

## Google Sheets Setup

1. In Google Cloud, create a Service Account with Drive API and Sheets API enabled.  
2. Download the JSON key as `service_account.json` into the project root.  
3. Create a Google Sheet named `Lead Intelligence`.  
4. Add a worksheet named `companies`.  
5. Add headers in row 1 matching this exact order:

```
company_name | domain | hq_country | hq_city | firm_type | aum_estimate |
team_size | revenue_model | tech_orientation | pain_points | recent_activity |
summary | fit_reasoning | fit_score | fit_class | outreach_snippet | sources |
first_seen | last_seen
```

6. Share the Sheet with the service account email as Editor.

## First-time Playwright Login (optional but useful)

If you need authenticated scraping (e.g., behind login):

- Implement a small `login_fn(page)` that navigates and logs in.
- Run `playwright_run_login_and_save_state(login_fn)` once to capture cookies into `pw_storage_state.json`.
- Subsequent runs load this state headless.

If you only hit public pages, skip this.

## Running

Edit the seed domains in `main()`:

```python
domains = ["aspectcapital.com", "aqr.com"]
```

Execute:

```
python lead_pipeline_v0.py
```

Behavior:

- Try `requests` on `/about`, then `/`.  
- If content is short or empty, fallback to Playwright headless on `/`.  
- Call Gemini with the strict schema.  
- Append a row to Sheets if the domain is not already present.

## How It Works

1. `scrape_with_requests` fetches and parses visible text from p, li, h1-3.  
2. If weak signal, `scrape_with_playwright` renders the page, then parses.  
3. `llm_icp_analysis` sends a single prompt to Gemini with the JSON schema of `Company_Profile`.  
4. The parsed result is validated by Pydantic.  
5. `save_company_row` appends a normalized row to Sheets.  
6. Duplicate domains are skipped.

## The Schema (Pydantic)

Key fields enforced:

- Identity: `company_name`, `domain`  
- Location: `hq_country`, `hq_city`  
- Firm: `firm_type`, `aum_estimate`, `team_size`, `revenue_model`  
- Signals: `tech_orientation`, `pain_points`, `recent_activity`  
- Decision: `summary`, `fit_reasoning`, `fit_score` (0-100), `fit_class` (High|Medium|Low)  
- Outreach: `outreach_snippet`  
- Provenance: `sources` (list of URLs), `first_seen`, `last_seen`

Domain must include a dot. Unknowns must be null, not guessed.

## Sheet Columns Reference

Order is fixed and must match:

```
SHEET_COLUMNS = [
  "company_name", "domain", "hq_country", "hq_city", "firm_type", "aum_estimate",
  "team_size", "revenue_model", "tech_orientation", "pain_points", "recent_activity",
  "summary", "fit_reasoning", "fit_score", "fit_class", "outreach_snippet", "sources",
  "first_seen", "last_seen"
]
```

Lists are written as comma-separated strings.

## Model Configuration

Default:

```python
response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=user_prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Company_Profile.model_json_schema(),
        temperature=0.2,
    )
)
```

Swap the `model` string if you need a different Gemini variant that supports JSON schema output. Keep `response_mime_type` and `response_schema` intact.

## Logging

Set `LOG_LEVEL` to `logging.DEBUG` for verbose traces. Output goes to stdout.

## Rate Limits and Timeouts

- `HTTP_TIMEOUT` controls requests timeout in seconds.  
- `SHEET_SLEEP` adds a short delay after appending to reduce API flakiness.  
- Playwright waits for `domcontentloaded` then retries with `networkidle`.

## Extending

- Add more paths to probe before Playwright.  
- Insert a robots-aware fetcher if you need to respect crawl rules.  
- Add upsert behavior: locate an existing row by domain and update instead of append.  
- Add CLI args with `argparse` for domains, sheet name, and headless toggle.  
- Capture and store per-domain last HTML snapshot for audit.

## Troubleshooting

- `GEMINI_API_KEY missing`  
  Add it to `.env`. Confirm key validity.

- `requests failed` or `Timeout`  
  Domain blocks bots or is slow. Playwright fallback should handle it. Increase `HTTP_TIMEOUT`.

- `Playwright timeout`  
  Some pages never reach idle. Raise the timeout or change `wait_until`.

- `Row for Domain already exists`  
  The domain is already in the sheet. Remove it or switch to upsert logic.

- `LLM analysis returned empty result`  
  Check API key, model name, network. Lower temperature if outputs drift off schema.

- `gspread auth errors`  
  Sheet not shared with the service account. Wrong `SERVICE_ACCOUNT_FILE` path. Wrong sheet or tab names.

## Security

- Keep `service_account.json` and `.env` out of version control.  
- Do not log secrets.  
- Treat `pw_storage_state.json` as sensitive. It can contain auth cookies.

## License

Proprietary or insert your license.

## Credits

Playwright, BeautifulSoup, Pydantic, gspread, Google Gemini.
