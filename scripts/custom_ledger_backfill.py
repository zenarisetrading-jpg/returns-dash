#!/usr/bin/env python3
import os
import sys
import time
import subprocess
from datetime import date, timedelta
from pathlib import Path
import psycopg2
import requests
import csv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from supabase import create_client

client_id = "nothing_silly"
lookback_days = 30
RATE_LIMIT = 62

db_url = os.getenv("DATABASE_URL")
supa_url = os.getenv("REACT_APP_SUPABASE_URL")
supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supa_url, supa_key)

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

def ingest_ledger(conn, account, content):
    lines = content.strip().split('\n')
    if not lines: return
    reader = csv.DictReader(lines, delimiter='\t')
    with conn.cursor() as cur:
        for row in reader:
            date_str = row.get("Date")
            if not date_str: continue
            if "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    date_str = f"{parts[2]}-{parts[0]}-{parts[1]}"
            country = row.get("Country")
            if country == "AE": country = "UAE"
            elif country == "SA": country = "KSA"

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
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT lwa_refresh_token, marketplace_id, region_endpoint FROM client_settings WHERE client_id = %s", (client_id,))
            row = cur.fetchone()
            if not row:
                sys.exit("Account not found")
            refresh_token, marketplace_id, region_endpoint = row
            
            marketplace_id = marketplace_id or os.getenv("MARKETPLACE_ID_UAE", "A2VIGQ35RCS4UG")
            region_endpoint = region_endpoint or "sellingpartnerapi-eu.amazon.com"
            endpoint = f"https://{region_endpoint}" if not region_endpoint.startswith("http") else region_endpoint

    today = date.today()
    window_start = today - timedelta(days=lookback_days)
    yesterday = today - timedelta(days=1)
        
    # Check bucket to see what's already downloaded
    files = supabase.storage.from_("ingestion-raw").list(client_id)
    downloaded = [f['name'] for f in files if 'LEDGER' in f['name']]
    
    needed_dates = []
    d = window_start
    while d <= yesterday:
        date_str = d.isoformat()
        expected = f"LEDGER_{date_str}_to_{date_str}.tsv"
        if expected not in downloaded:
            needed_dates.append(date_str)
        d += timedelta(days=1)

    print(f"Missing {len(needed_dates)} ledger dates for {client_id}")

    token_generated_at = 0.0
    token = ""
    last_submit_ts = 0.0

    with psycopg2.connect(db_url) as conn:
        for m_date in needed_dates:
            if time.monotonic() - token_generated_at > 3000:
                token = _generate_spapi_token(refresh_token)
                token_generated_at = time.monotonic()
                print("Generated fresh token")

            env = os.environ.copy()
            env["SP_API_TOKEN"] = token
            env["SP_API_ENDPOINT"] = endpoint
            env["ACCOUNT_ID"] = client_id
            env["START_DATE"] = m_date
            env["END_DATE"] = m_date
            env["MARKETPLACE_ID_UAE"] = marketplace_id
            
            elapsed = time.monotonic() - last_submit_ts
            if elapsed < RATE_LIMIT and last_submit_ts > 0:
                time.sleep(RATE_LIMIT - elapsed)
                
            print(f"Pulling Ledger for {m_date}...")
            try:
                subprocess.run(
                    [sys.executable, str(ROOT / "transformations" / "finance_spapi.py")],
                    env=env, check=True
                )
                
                # Now ingest it immediately
                file_name = f"LEDGER_{m_date}_to_{m_date}.tsv"
                print(f"  Ingesting {file_name} into DB...")
                res = supabase.storage.from_("ingestion-raw").download(f"{client_id}/{file_name}")
                content = res.decode('utf-8')
                ingest_ledger(conn, client_id, content)
                conn.commit()
                print(f"  Success!")
            except subprocess.CalledProcessError as e:
                print(f"  [!] Pull failed for {m_date}")
            except Exception as e:
                print(f"  [!] Ingestion failed for {m_date}: {e}")
                conn.rollback()
                
            last_submit_ts = time.monotonic()

if __name__ == "__main__":
    main()
