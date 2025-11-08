"""
lead_pipeline_v0.py
Single-file Lead Intelligence skeleton with Playwright cookie support + Google Sheets.
- Install: pip install playwright gspread oauth2client beautifulsoup4 requests
- Playwright post-install: playwright install
- Create GCP service account JSON and share your Sheet with the service account email
- Create a Google Sheet with a "companies" worksheet and headers matching the `SHEET_COLUMNS`
"""


from dotenv import load_dotenv
import os
import time
import json
import logging,sys
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from google import genai
from google.genai import types
from dataclasses import dataclass
from pydantic import BaseModel, Field,HttpUrl, field_validator
from typing import Optional, List, Literal
from datetime import date

# Playwright (sync API)
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeout,Playwright, BrowserContext

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIG ---

LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s",handlers=[logging.StreamHandler(sys.stdout)],
    force=True)
logging.getLogger().info("Boot sanity-check")

SERVICE_ACCOUNT_FILE = "service_account.json"
SHEET_NAME = "Lead Intelligence"
COMPANIES_SHEET_NAME = "companies"

# Playwright storage-state file (holds cookies + localStorage). One file per login/user is handy.
PLAYWRIGHT_STATE_FILE = "pw_storage_state.json"

# Rate limits
SHEET_SLEEP = 1.2
HTTP_TIMEOUT = 15


# Column ordering for the sheet (ensure your Sheet has these headers in the same order)
SHEET_COLUMNS = [
    "company_name", "domain", "hq_country", "hq_city", "firm_type", "aum_estimate",
    "team_size", "revenue_model", "tech_orientation", "pain_points", "recent_activity",
    "summary", "fit_reasoning", "fit_score", "fit_class", "outreach_snippet", "sources",
    "first_seen", "last_seen"
]

load_dotenv()

class Company_Profile(BaseModel):
    company_name: str = Field(
        description="Official company name as listed on their website or public filings."
    )
    domain: str = Field(
        description="Primary company domain (e.g., 'man.com', 'aqr.com')."
    )
    hq_country: Optional[str] = Field(
        default=None,
        description="Country where the company’s headquarters are located."
    )
    hq_city: Optional[str] = Field(
        default=None,
        description="City of the company’s headquarters, if available."
    )
    firm_type: Optional[Literal[
        "hedge_fund", "prop_trading", "asset_manager",
        "family_office", "crypto_fund", "broker", "data_vendor", "other"
    ]] = Field(
        default=None,
        description="Type of firm or business category most closely describing the company."
    )
    aum_estimate: Optional[str] = Field(
        default=None,
        description="Approximate Assets Under Management (AUM), if disclosed (e.g., '$5B')."
    )
    team_size: Optional[str] = Field(
        default=None,
        description="Approximate size of the team or organization (e.g., '10–25 employees')."
    )
    revenue_model: Optional[str] = Field(
        default=None,
        description="Brief note on how the company generates revenue (e.g., 'management + performance fees')."
    )
    tech_orientation: Optional[str] = Field(
        default=None,
        description="Indication of how the company uses technology (e.g., 'AI-driven quant research')."
    )
    pain_points: Optional[str] = Field(
        default=None,
        description="Summary of potential technical or operational challenges the company faces."
    )
    recent_activity: Optional[str] = Field(
        default=None,
        description="Summary of recent company news, launches, or hires (<12 months old)."
    )
    summary: str = Field(
        description="1-2 sentence overview describing what the company does, where it operates, and scale."
    )
    fit_reasoning: str = Field(
        description="Concise reasoning for why this company fits (or does not fit) the ICP criteria."
    )
    fit_score: int = Field(
        ge=0, le=100,
        description="Numeric score (0–100) expressing how well this company aligns with the ICP."
    )
    fit_class: Literal["High", "Medium", "Low"] = Field(
        description="Categorical fit class derived from fit_score and ICP reasoning."
    )
    outreach_snippet: str = Field(
        description="1–2 sentence personalised outreach message referencing recent activity or fit context.Try and use recent news about the company within the description to engage the recipient"
    )
    sources: List[str] = Field(
        description="List of one or more source URLs used to validate the profile."
    )
    first_seen: Optional[str] = Field(
        default=None,
        description="Date (YYYY-MM-DD) when this company was first captured in the pipeline."
    )
    last_seen: Optional[str] = Field(
        default=None,
        description="Most recent date (YYYY-MM-DD) the company profile was updated or verified."
    )

    @field_validator("domain")
    @classmethod
    def domain_ok(cls,v):
        if "." not in v:
            raise ValueError("Invalid Domain")
        return v

# --- SHEETS AUTH (gspread) ---
def init_sheets():

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE,scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME)
    companies_ws = sheet.worksheet(COMPANIES_SHEET_NAME)
    return companies_ws


# --- PLAYWRIGHT HELPERS ---
def ensure_playwright_storage_exists():
    """Create an empty storage file if none exists (first-time)."""
    if not os.path.exists(PLAYWRIGHT_STATE_FILE):
    #  create minimal valid JSON storage (playwright will populate after you login via browser)
        with open(PLAYWRIGHT_STATE_FILE, "w") as f:
            json.dump({}, f)
            logging.info(f"Created empty Playwright storage state: {PLAYWRIGHT_STATE_FILE}")


def playwright_run_login_and_save_state(login_fn):
    """
    Run a headful browser so you can log in manually, then save storage state.
    Example: call this once to login to LinkedIn or another site.
    """
    ensure_playwright_storage_exists()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)# headful so you can interact
        context = browser.new_context()
        page = context.new_page()
        logging.info("Open the browser window and perform the login steps now...")
        login_fn(page)# callback should perform navigation + wait until logged in
        # Wait a bit and let cookies settle
        time.sleep(2)
        context.storage_state(path=PLAYWRIGHT_STATE_FILE)
        logging.info(f"Saved storage = state to {PLAYWRIGHT_STATE_FILE}")
        browser.close()


def launch_playwright_browser(headless=True) -> tuple[Playwright, Browser, BrowserContext]:
    """
    Launch a Playwright browser context using saved storage state (cookies/localStorage).
    Returns (browser, context)
    """ 
    ensure_playwright_storage_exists()
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    # load storage state into context to preserve cookies/localStorage
    context = browser.new_context(storage_state=PLAYWRIGHT_STATE_FILE if os.path.exists(PLAYWRIGHT_STATE_FILE) else None)
    return pw,browser, context

def close_playwright(pw, browser):
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass

def scrape_with_playwright(domain: str, path: str = "/", timeout_s: int = 15) -> str:
    """
    Return rendered page text (text from <p> and <li>) using Playwright context (with cookies).
    Use this when the page needs JS or requires being logged in.
    """
    url = f"https://{domain.rstrip('/')}{path}"
    pw,browser,context = None, None, None
    try:
        pw,browser,context = launch_playwright_browser(headless=True)
        page = context.new_page()
        logging.info(f"[Playwright] Navigating to {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        except PlaywrightTimeout:
            logging.warning(f"domcontentloaded timeout, trying networkidle")
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
        time.sleep(2.0)
       
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        text = " ".join(t.get_text(" ", strip=True) for t in soup.select("p,li"))
        return text[:10000] # cap
    
    except PlaywrightTimeout as e:
        logging.warning(f"Playwright timeout for {url}: {e}")
        return ""
    
    except Exception as e:
        logging.error(f"Playwright scrape error {url}: {e}")
        return ""
    
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        
# --- STATIC SCRAPER FALLBACK (requests + BeautifulSoup) ---       
def scrape_with_requests(domain: str, path: str = "/") -> str:
    url = f"https://{domain.rstrip('/')}{path}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT, headers=headers,allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script","style"]):
            script.decompose()




        text = " ".join(t.get_text(" ",strip=True) for t in soup.select("p,li,h1,h2,h3"))
        return text[:10000]
    except requests.Timeout:
        logging.warning(f"Timeout for {url}")
        return ""
    except requests.RequestException as e:
        logging.warning(f"requests failed for {url}: {e}")
        return ""
    

def to_row(self):
    """Return a list of values matching SHEET_COLUMNS order."""
    return [getattr(self,col,"") for col in SHEET_COLUMNS]
    
# --- LLM STUB (replace with your model call) ---

def llm_icp_analysis(company_name: str, today: str) -> Dict:
    from dotenv import load_dotenv
    from google.genai import types

    load_dotenv()  # ensures .env values are loaded even if run standalone
    API_KEY = os.getenv("GEMINI_API_KEY")
    

    if not API_KEY:
        logging.error("GEMINI_API_KEY missing")
        return {}
  
    logging.info("Gemini key present: True")

    logging.info(f"Loaded key: {API_KEY[:6]}...")
    schema = Company_Profile.model_json_schema()
    client = genai.Client(api_key=API_KEY)

    user_prompt = f""" System / Instruction:
    You are assisting with institutional user discovery for an AI trading platform targeting mid-market funds. 
    -Return ONLY JSON that validates against the provided response_schema. 
    -Actively use Google Search when facts are missing (AUM, HQ city/country, team size, recent news).
    -Cite the exact URLs you used in `sources` (prefer official site, filings, reputable press).
    -If a field isn’t on the official site, check press releases, reputable news, or recent job posts.
    -If you still cannot verify, set the field to null—do not guess.
    -For AUM/team size, use ranges with sources (e.g., ‘$50–60B’; ‘1000–1500’) if exact numbers vary by source
    -Use 1–2 recent items (<12 months) for recent_activity and cite the URL.

    Ideal Customer Profile (ICP) summary:
    - Firm types: hedge fund, prop firm, asset manager, crypto fund, family office in US/UK/EU/CA.
    - Size: typically > $10m AUM or > $1m annual revenue.
    - Team: quant/data science/trading engineering present; lean infra (not massive internal platform teams).
    - Pain points to look for: infra bottlenecks, tech debt, slow strategy deployment, fragmented systems.
    - Tech maturity: using or trialing algorithmic trading/AI/quant platforms.
    - Geography: US, UK, EU, Canada.

    Task:
    Determine if “{company_name}” should be contacted during user-discovery and craft a personalised 1-2 sentence outreach snippet based on RECENT public activity (prefer < 12 months).Today is {today}.
    Score 0–100 and classify as High/Medium/Low based on ICP alignment and recency/strength of activity.

    Output policy:
    - Be precise, concise, non-promotional.
    - Use ISO dates (YYYY-MM-DD) for first_seen/last_seen ({today} for last_seen).
    - ‘recent_activity’ (< 12 months).
    - ‘summary’ (2-4 sentences).
    - ‘outreach_snippet’ personalised message,should be engaging and should reference 'sources'.

    """
    try:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        )
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=user_prompt,
            config=config)
        client.close()

        if response.parsed:
                parsed = response.parsed
        elif response.text:
            parsed = json.loads(response.text)
        else:
            logging.error(f"Empty response from Gemini for {company_name}")
            return {}
        
        obj = Company_Profile.model_validate(parsed)
        return obj.model_dump()
            
    except Exception as e:
        logging.error(f"LLM analysis failed for {company_name}: {e}")
        client.close()
        return {}




def get_seen_domains(ws) -> set[str]:
    idx = SHEET_COLUMNS.index("domain") + 1
    vals = ws.col_values(idx)[1:]
    return {v.strip().lower() for v in vals}
    
# --- SHEETS WRITER (append/update) ---
def save_company_row(ws,row_dict: dict[str, object]) -> None:
    """
    Append-only mode (simple). If you want upsert behavior, call get_seen_domains and update logic.
    """
    # Build row following SHEET_COLUMNS
  
    existing_domains = get_seen_domains(ws)
    domain = (row_dict.get("domain") or "").strip().lower()
    if domain in existing_domains:
        raise ValueError(f"Row for Domain: {domain} already exists")

    # Build row following SHEET_COLUMNS, converting lists to comma-separated strings
    row = []
    for col in SHEET_COLUMNS:
        value = row_dict.get(col, "")
        # Convert lists to comma-separated strings for sheets
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        row.append(value)

    ws.append_row(row, value_input_option="RAW")
    time.sleep(SHEET_SLEEP)
    logging.info(f"Appended row for {row_dict.get('domain','<none>')}")

# --- MAIN PROCESSING FLOW ---
def process_domain(domain: str, ws):  
    """
    Orchestration for a single domain:
    - Try requests scrape first (fast)
    - If result empty or dynamic site suspected, run Playwright
    - Run LLM analysis (stub)
    - Save row to sheet
    """
    logging.info(f"Processing {domain}")
    about_text = scrape_with_requests(domain, "/about") or scrape_with_requests(domain, "/")
    used_playwright = False
    if not about_text or len(about_text) < 200:
        # fallback to Playwright for rendered JS or protected content
        logging.info("Falling back to Playwright for rendered content")
        about_text = scrape_with_playwright(domain, "/")
        used_playwright = True
    
    today = time.strftime("%Y-%m-%d")
    analysis = llm_icp_analysis(domain, today)
    if not analysis:
        raise RuntimeError("LLM analysis returned empty result (check API key/model).")

    row = {
    "company_name": analysis.get("company_name", domain.split(".")[0].title()),
    "domain": analysis.get("domain", domain),
    "hq_country": analysis.get("hq_country", ""),
    "hq_city": analysis.get("hq_city", ""),
    "firm_type": analysis.get("firm_type", ""),
    "aum_estimate": analysis.get("aum_estimate", ""),
    "team_size": analysis.get("team_size", ""),
    "revenue_model": analysis.get("revenue_model", ""),
    "tech_orientation": analysis.get("tech_orientation", ""),
    "pain_points": analysis.get("pain_points", ""),
    "recent_activity": analysis.get("recent_activity", ""),
    "summary": analysis.get("summary", "") + (f" [rendered]" if used_playwright else ""),
    "fit_reasoning": analysis.get("fit_reasoning", ""),
    "fit_score": analysis.get("fit_score", ""),
    "fit_class": analysis.get("fit_class", ""),
    "outreach_snippet": analysis.get("outreach_snippet", ""),
    "sources": analysis.get("sources", [f"https://{domain}"]),
    "first_seen": analysis.get("first_seen", today),
    "last_seen": analysis.get("last_seen", today)
}
    save_company_row(ws, row)

# --- Simple CLI-style main ---
def main():
    logging.info("Starting pipeline…")
    domains = ["aspectcapital.com","aqr.com"]
    ws = init_sheets()
    seen = get_seen_domains(ws)

    for d in domains:
        if d in seen:
            logging.info(f"Skipping {d} (already seen)")
            continue 
        try:
            process_domain(d,ws)
        except Exception as e:
            logging.error(f"Failed processing {d}: {e}")
             
if __name__ == "__main__":
    try:
        logging.info("Entrypoint reached — calling main()")
        main()
    except Exception:
        logging.exception("Unhandled exception in main")
        raise