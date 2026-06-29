#!/usr/bin/env python3
"""
Saddle Returns and Finance Pipeline
===================================
Runs gap-detection and sequential extraction for Returns and Finance.
It loops through authorized accounts and triggers the respective SP-API scripts
to download TSVs into the Supabase ingestion-raw bucket.
"""

import logging
import os
import sys
import subprocess
import requests
import csv
from datetime import date, timedelta
from pathlib import Path
import psycopg2
from supabase import create_client

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
log = logging.getLogger("saddl.returns_finance")

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

    # Note: Using `fact_returns` to check what dates we have.
    # If the backfill inserted `return_date`, we query that.
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT return_date::date
                FROM returns.fact_returns
                WHERE saddl_id = %s
                  AND return_date >= %s
                  AND return_date <= %s
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

def _ingest_returns(conn, account: str, content: str):
    lines = content.strip().split('\n')
    if not lines:
        return
    reader = csv.DictReader(lines, delimiter='\t')
    with conn.cursor() as cur:
        for row in reader:
            return_date = row.get("return-date", "").split("T")[0]
            if not return_date:
                continue
            country = "KSA" if "ksa" in account.lower() else "UAE"
            reference_id = row.get("order-id")
            cur.execute("""
                INSERT INTO returns.fact_returns (
                    return_date, asin, msku, fnsku, title, quantity, 
                    fulfillment_center, disposition, reason, customer_comments, saddl_id, synced_at,
                    reference_id, country, event_type
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, 'CustomerReturns'
                ) ON CONFLICT (reference_id, country, saddl_id) DO NOTHING
            """, (
                return_date, row.get("asin"), row.get("sku"), row.get("fnsku"),
                row.get("product-name"), int(row.get("quantity", 0)) if row.get("quantity") else 0,
                row.get("fulfillment-center-id"), row.get("detailed-disposition"),
                row.get("reason"), row.get("customer-comments"), account, reference_id, country
            ))

def _ingest_ledger(conn, account: str, content: str):
    lines = content.strip().split('\n')
    if not lines:
        return
    reader = csv.DictReader(lines, delimiter='\t')
    with conn.cursor() as cur:
        for row in reader:
            date_str = row.get("Date")
            if not date_str:
                continue
            if "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    date_str = f"{parts[2]}-{parts[0]}-{parts[1]}"
            country = row.get("Country")
            if country == "AE":
                country = "UAE"
            elif country == "SA":
                country = "KSA"
            cur.execute("""
                INSERT INTO returns.fact_returns (
                    return_date, asin, msku, fnsku, title, event_type, reference_id,
                    quantity, fulfillment_center, disposition, reason, country,
                    reconciled_quantity, unreconciled_quantity, saddl_id, synced_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                ) ON CONFLICT ON CONSTRAINT fact_returns_unique_event DO NOTHING
            """, (
                date_str, row.get("ASIN"), row.get("MSKU"), row.get("FNSKU"), row.get("Title"),
                row.get("Event Type"), row.get("Reference ID") if row.get("Reference ID") else None,
                int(row.get("Quantity", 0)) if row.get("Quantity") not in (None, "") else 0,
                row.get("Fulfillment Center"), row.get("Disposition"), row.get("Reason"), country,
                int(row.get("Reconciled Quantity", 0)) if row.get("Reconciled Quantity") not in (None, "") else None,
                int(row.get("Unreconciled Quantity", 0)) if row.get("Unreconciled Quantity") not in (None, "") else None,
                account
            ))

def main():
    log.info("═══════════════════════════════════════════════════════════")
    log.info("  Saddle Returns & Finance Daily Pipeline")
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

        # Loop over missing dates and execute python scripts as subprocesses
        last_submit_ts = 0.0
        RATE_LIMIT = 62

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
            
            # 1. Run Returns Extractor & Ingestion
            elapsed = time.monotonic() - last_submit_ts
            if elapsed < RATE_LIMIT and last_submit_ts > 0:
                time.sleep(RATE_LIMIT - elapsed)
            
            log.info(f"    -> [RETURNS] Pulling {m_date}")
            pull_success = False
            try:
                subprocess.run(
                    [sys.executable, str(ROOT / "transformations" / "returns_spapi.py")],
                    env=env, check=True
                )
                pull_success = True
            except subprocess.CalledProcessError as e:
                log.error(f"    [!] Returns pull failed for {m_date}: {e}")
                if e.returncode == 43:
                    log.warning(f"    [!] Account {client_id} is unauthorized (403 Forbidden). Skipping remaining dates for this account.")
                    break
            last_submit_ts = time.monotonic()
            
            if pull_success:
                try:
                    file_name = f"FBA_RETURNS_{m_date}_to_{m_date}.tsv"
                    local_path = ROOT / "data" / "tmp" / file_name
                    content = None
                    if local_path.exists():
                        try:
                            content = local_path.read_text(encoding='utf-8')
                            # Clean up local file after reading
                            local_path.unlink()
                            log.info(f"    -> [RETURNS] Read {file_name} from local temp file.")
                        except Exception as local_read_err:
                            log.warning(f"    [!] Failed to read local temp file: {local_read_err}")
                    
                    if content is None:
                        supa_url = os.getenv("REACT_APP_SUPABASE_URL") or os.getenv("SUPABASE_URL")
                        if not supa_url:
                            db_url = os.getenv("DATABASE_URL")
                            if db_url:
                                try:
                                    import urllib.parse
                                    parsed = urllib.parse.urlparse(db_url)
                                    username = parsed.username
                                    if username and '.' in username:
                                        project_ref = username.split('.')[-1]
                                        supa_url = f"https://{project_ref}.supabase.co"
                                except Exception:
                                    pass
                        supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("REACT_APP_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
                        supabase = create_client(supa_url, supa_key)
                        res = supabase.storage.from_("ingestion-raw").download(f"{client_id}/{file_name}")
                        content = res.decode('utf-8')
                        log.info(f"    -> [RETURNS] Downloaded {file_name} from Supabase storage.")

                    with psycopg2.connect(_db_url()) as conn:
                        _ingest_returns(conn, client_id, content)
                        conn.commit()
                    log.info(f"    -> [RETURNS] Ingested {file_name} successfully into DB.")
                except Exception as ingest_err:
                    log.error(f"    [!] Returns ingestion failed for {m_date}: {ingest_err}")

            # 2. Run Finance Extractor & Ingestion
            elapsed = time.monotonic() - last_submit_ts
            if elapsed < RATE_LIMIT and last_submit_ts > 0:
                time.sleep(RATE_LIMIT - elapsed)
                
            log.info(f"    -> [FINANCE] Pulling {m_date}")
            pull_success = False
            try:
                subprocess.run(
                    [sys.executable, str(ROOT / "transformations" / "finance_spapi.py")],
                    env=env, check=True
                )
                pull_success = True
            except subprocess.CalledProcessError as e:
                log.error(f"    [!] Finance pull failed for {m_date}: {e}")
                if e.returncode == 43:
                    log.warning(f"    [!] Account {client_id} is unauthorized (403 Forbidden). Skipping remaining dates for this account.")
                    break
            last_submit_ts = time.monotonic()

            if pull_success:
                try:
                    file_name = f"LEDGER_{m_date}_to_{m_date}.tsv"
                    local_path = ROOT / "data" / "tmp" / file_name
                    content = None
                    if local_path.exists():
                        try:
                            content = local_path.read_text(encoding='utf-8')
                            # Clean up local file after reading
                            local_path.unlink()
                            log.info(f"    -> [FINANCE] Read {file_name} from local temp file.")
                        except Exception as local_read_err:
                            log.warning(f"    [!] Failed to read local temp file: {local_read_err}")
                    
                    if content is None:
                        supa_url = os.getenv("REACT_APP_SUPABASE_URL") or os.getenv("SUPABASE_URL")
                        if not supa_url:
                            db_url = os.getenv("DATABASE_URL")
                            if db_url:
                                try:
                                    import urllib.parse
                                    parsed = urllib.parse.urlparse(db_url)
                                    username = parsed.username
                                    if username and '.' in username:
                                        project_ref = username.split('.')[-1]
                                        supa_url = f"https://{project_ref}.supabase.co"
                                except Exception:
                                    pass
                        supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("REACT_APP_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
                        supabase = create_client(supa_url, supa_key)
                        res = supabase.storage.from_("ingestion-raw").download(f"{client_id}/{file_name}")
                        content = res.decode('utf-8')
                        log.info(f"    -> [FINANCE] Downloaded {file_name} from Supabase storage.")

                    with psycopg2.connect(_db_url()) as conn:
                        _ingest_ledger(conn, client_id, content)
                        conn.commit()
                    log.info(f"    -> [FINANCE] Ingested {file_name} successfully into DB.")
                except Exception as ingest_err:
                    log.error(f"    [!] Finance ingestion failed for {m_date}: {ingest_err}")



    log.info("═══════════════════════════════════════════════════════════")
    log.info("  Done.")
    log.info("═══════════════════════════════════════════════════════════")

if __name__ == "__main__":
    main()
