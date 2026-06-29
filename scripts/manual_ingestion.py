import os
import sys
import csv
import psycopg2
from supabase import create_client
from dotenv import load_dotenv

# Load env vars
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

db_url = os.getenv("DATABASE_URL")
if not db_url:
    sys.exit("Missing DATABASE_URL")

supa_url = os.getenv("REACT_APP_SUPABASE_URL")
supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not supa_url or not supa_key:
    sys.exit("Missing Supabase credentials")

supabase = create_client(supa_url, supa_key)
bucket = "ingestion-raw"

# Accounts to process
accounts = ["aurio_uae", "s2c_uae_test", "oneshot_uae", "nothing_silly"]

def ingest_returns(conn, account, file_name, content):
    """Ingest FBA_RETURNS into returns.fact_returns"""
    lines = content.strip().split('\n')
    if not lines: return
    
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
                return_date,
                row.get("asin"),
                row.get("sku"),
                row.get("fnsku"),
                row.get("product-name"),
                int(row.get("quantity", 0)) if row.get("quantity") else 0,
                row.get("fulfillment-center-id"),
                row.get("detailed-disposition"),
                row.get("reason"),
                row.get("customer-comments"),
                account,
                reference_id,
                country
            ))

def ingest_ledger(conn, account, file_name, content):
    """Ingest LEDGER into returns.fact_returns (as event_type records)"""
    lines = content.strip().split('\n')
    if not lines: return
    
    reader = csv.DictReader(lines, delimiter='\t')
    
    with conn.cursor() as cur:
        for row in reader:
            date_str = row.get("Date")
            if not date_str:
                continue
                
            # Convert MM/DD/YYYY to YYYY-MM-DD
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
                date_str,
                row.get("ASIN"),
                row.get("MSKU"),
                row.get("FNSKU"),
                row.get("Title"),
                row.get("Event Type"),
                row.get("Reference ID") if row.get("Reference ID") else None,
                int(row.get("Quantity", 0)) if row.get("Quantity") not in (None, "") else 0,
                row.get("Fulfillment Center"),
                row.get("Disposition"),
                row.get("Reason"),
                country,
                int(row.get("Reconciled Quantity", 0)) if row.get("Reconciled Quantity") not in (None, "") else None,
                int(row.get("Unreconciled Quantity", 0)) if row.get("Unreconciled Quantity") not in (None, "") else None,
                account
            ))

def main():
    with psycopg2.connect(db_url) as conn:
        for account in accounts:
            print(f"Processing TSVs for {account}...")
            files = supabase.storage.from_(bucket).list(account)
            
            for f in files:
                name = f['name']
                if name.endswith('.tsv'):
                    print(f"  Downloading {name}...")
                    try:
                        res = supabase.storage.from_(bucket).download(f"{account}/{name}")
                        content = res.decode('utf-8')
                        
                        if 'FBA_RETURNS' in name:
                            ingest_returns(conn, account, name, content)
                        elif 'LEDGER' in name:
                            pass # We already ingested LEDGER
                            
                        conn.commit()
                        print(f"    -> Ingested {name}")
                    except Exception as e:
                        print(f"    [!] Failed to ingest {name}: {e}")
                        conn.rollback()

if __name__ == "__main__":
    main()
