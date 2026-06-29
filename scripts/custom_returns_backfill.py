import os
import sys
import time
import subprocess
from pathlib import Path
import psycopg2
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def get_db_url():
    return os.getenv("DATABASE_URL")

def get_account_info(account_id):
    with psycopg2.connect(get_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lwa_refresh_token, marketplace_id, region_endpoint
                FROM client_settings
                WHERE client_id = %s
            """, (account_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Account {account_id} not found")
            return {
                "refresh_token": row[0],
                "marketplace_id": row[1] or "A2VIGQ35RCS4UG",
                "region_endpoint": row[2] or "sellingpartnerapi-eu.amazon.com",
            }

def generate_token(refresh_token):
    client_id = os.getenv("LWA_CLIENT_ID")
    client_secret = os.getenv("LWA_CLIENT_SECRET")
    resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def backfill_account(account_id, date_ranges):
    info = get_account_info(account_id)
    token = generate_token(info["refresh_token"])
    endpoint = f"https://{info['region_endpoint']}" if not info['region_endpoint'].startswith("http") else info['region_endpoint']
    
    for start, end in date_ranges:
        print(f"Backfilling {account_id} from {start} to {end}...")
        env = os.environ.copy()
        env["SP_API_TOKEN"] = token
        env["SP_API_ENDPOINT"] = endpoint
        env["ACCOUNT_ID"] = account_id
        env["START_DATE"] = start
        env["END_DATE"] = end
        env["MARKETPLACE_ID_UAE"] = info["marketplace_id"]
        
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "transformations" / "returns_spapi.py")],
                env=env, check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed for {start} to {end}: {e}")
        
        # Rate limit to avoid 429s for Reports API
        time.sleep(62)

def main():
    date_ranges = [
        ("2026-02-23", "2026-03-25"),
        ("2026-03-25", "2026-04-24"),
        ("2026-04-24", "2026-05-24"),
        ("2026-05-24", "2026-06-23")
    ]
    
    # nothing_silly needs full backfill
    backfill_account("nothing_silly", date_ranges)
    
    # oneshot_ksa already has up to April 24, but running full is fine if they overwrite 
    # Actually, we can just run the last two for ksa to save time
    ksa_ranges = [
        ("2026-04-24", "2026-05-24"),
        ("2026-05-24", "2026-06-23")
    ]
    backfill_account("oneshot_ksa", ksa_ranges)
    
    # Run manual ingestion to insert the newly downloaded TSVs into the DB
    print("Ingesting newly downloaded TSVs...")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "manual_ingestion.py")], check=True)

if __name__ == "__main__":
    main()
