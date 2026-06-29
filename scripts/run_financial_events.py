#!/usr/bin/env python3
"""
Saddle Financial Events Daily Pipeline
======================================
Runs gap-detection and sequential extraction for order-level transaction fees,
commissions, sales revenue, refunds, and adjustments.
"""

import logging
import os
import sys
import subprocess
import requests
from datetime import date, timedelta
from pathlib import Path
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("saddl.financial_events")

LOOKBACK_DAYS = 30

def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        sys.exit("❌  DATABASE_URL is not set.")
    return url

def _fetch_active_accounts() -> list[dict]:
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT client_id, lwa_refresh_token, marketplace_id, region_endpoint
                FROM client_settings
                WHERE onboarding_status = 'active'
                  AND lwa_refresh_token IS NOT NULL
            """
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {
            "client_id":       r[0],
            "refresh_token":   r[1],
            "marketplace_id":  r[2] or os.getenv("MARKETPLACE_ID_UAE", "A2VIGQ35RCS4UG"),
            "region_endpoint": r[3] or "sellingpartnerapi-eu.amazon.com",
        }
        for r in rows
    ]

def _find_missing_dates(client_id: str, lookback_days: int = LOOKBACK_DAYS) -> list[str]:
    today = date.today()
    window_start = today - timedelta(days=lookback_days)
    yesterday = today - timedelta(days=1)

    # Find missing dates in shipment_events
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT posted_date::date
                FROM finance.shipment_events
                WHERE client_id = %s
                  AND posted_date >= %s
                  AND posted_date <= %s
            """, (client_id, window_start, yesterday))
            have = {r[0] for r in cur.fetchall()}

    all_dates = set()
    d = window_start
    while d <= yesterday:
        all_dates.add(d)
        d += timedelta(days=1)

    missing = sorted(all_dates - have)
    return [d.isoformat() for d in missing]

def _generate_spapi_token(refresh_token: str) -> str:
    lwa_client_id = os.getenv("LWA_CLIENT_ID", "")
    lwa_client_secret = os.getenv("LWA_CLIENT_SECRET", "")
    
    token_resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": lwa_client_id,
            "client_secret": lwa_client_secret,
        }
    )
    token_resp.raise_for_status()
    return token_resp.json()["access_token"]

def main():
    log.info("═══════════════════════════════════════════════════════════")
    log.info("  Saddle Financial Events Daily Pipeline")
    log.info("═══════════════════════════════════════════════════════════")

    accounts = _fetch_active_accounts()
    if not accounts:
        log.warning("No active accounts found.")
        sys.exit(0)

    for account in accounts:
        client_id = account["client_id"]
        log.info(f"Processing Account: {client_id}")
        
        missing_dates = _find_missing_dates(client_id)
        if not missing_dates:
            log.info(f"  [{client_id}] No missing dates found.")
            continue
            
        log.info(f"  [{client_id}] Found {len(missing_dates)} missing dates. Processing...")
        
        token_generated_at = 0.0
        token = ""
        endpoint = f"https://{account['region_endpoint']}" if not account['region_endpoint'].startswith("http") else account['region_endpoint']

        last_submit_ts = 0.0
        RATE_LIMIT = 5 # Standard limit on Finances v0 listFinancialEvents is 0.5 reqs/sec

        for m_date in missing_dates:
            import time
            
            # Regenerate token if it's older than 50 minutes (3000 seconds)
            if time.monotonic() - token_generated_at > 3000:
                try:
                    token = _generate_spapi_token(account["refresh_token"])
                    token_generated_at = time.monotonic()
                    log.info(f"  [{client_id}] Generated fresh SP-API Token.")
                except Exception as e:
                    log.error(f"  [{client_id}] Failed to generate token: {e}")
                    break
            
            env = os.environ.copy()
            env["SP_API_TOKEN"] = token
            env["SP_API_ENDPOINT"] = endpoint
            env["ACCOUNT_ID"] = client_id
            env["START_DATE"] = m_date
            env["END_DATE"] = m_date
            env["MARKETPLACE_ID_UAE"] = account["marketplace_id"]
            
            elapsed = time.monotonic() - last_submit_ts
            if elapsed < RATE_LIMIT and last_submit_ts > 0:
                time.sleep(RATE_LIMIT - elapsed)
            
            log.info(f"    -> [FINANCIAL EVENTS] Syncing {m_date}")
            try:
                subprocess.run(
                    [sys.executable, str(ROOT / "transformations" / "financial_events_spapi.py")],
                    env=env, check=True
                )
            except subprocess.CalledProcessError as e:
                log.error(f"    [!] Financial events sync failed for {m_date}: {e}")
                if e.returncode == 43:
                    log.warning(f"    [!] Account {client_id} is unauthorized (403 Forbidden). Skipping remaining dates for this account.")
                    break
            last_submit_ts = time.monotonic()

    log.info("═══════════════════════════════════════════════════════════")
    log.info("  Done.")
    log.info("═══════════════════════════════════════════════════════════")

if __name__ == "__main__":
    main()
