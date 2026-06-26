#!/usr/bin/env python3
"""inventory_age.py

Fetches the GET_FBA_INVENTORY_PLANNING_DATA report from SP-API, parses the TSV, 
aggregates inventory quantities by age buckets, and upserts them into Supabase.

Usage:
    python3 transformations/inventory_age.py
"""

import os
import sys
import time
import requests
import gzip
import csv
import io
from datetime import date

from supabase import create_client

def main():
    token = os.getenv("SP_API_TOKEN")
    endpoint = os.getenv("SP_API_ENDPOINT")
    account_id = os.getenv("ACCOUNT_ID")
    if not token or not endpoint or not account_id:
        print("Missing SP_API_TOKEN, SP_API_ENDPOINT, or ACCOUNT_ID", file=sys.stderr)
        sys.exit(1)

    supabase_url = os.getenv("REACT_APP_SUPABASE_URL")
    supabase_key = os.getenv("REACT_APP_SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        print("Missing Supabase credentials", file=sys.stderr)
        sys.exit(1)
        
    supabase = create_client(supabase_url, supabase_key)

    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json"
    }

    # 1. Request the report
    marketplace_id = "A2VIGQ35RCS4UG"  # Default to UAE
    if "ksa" in account_id.lower():
        marketplace_id = "A17E79C6D8DWNP"  # KSA

    print(f"Requesting FBA Inventory Planning Data report for marketplace {marketplace_id}...")
    create_url = f"{endpoint}/reports/2021-06-30/reports"
    payload = {
        "reportType": "GET_FBA_INVENTORY_PLANNING_DATA",
        "marketplaceIds": [marketplace_id]
    }
    resp = requests.post(create_url, headers=headers, json=payload)
    resp.raise_for_status()
    report_id = resp.json().get("reportId")
    print(f"Report ID: {report_id}")

    # 2. Poll until DONE
    print("Waiting for report to generate...")
    while True:
        poll_url = f"{endpoint}/reports/2021-06-30/reports/{report_id}"
        poll_resp = requests.get(poll_url, headers=headers)
        poll_resp.raise_for_status()
        status = poll_resp.json().get("processingStatus")
        if status in ["DONE", "CANCELLED", "FATAL"]:
            break
        time.sleep(15)

    if status != "DONE":
        print(f"Report failed with status: {status}")
        sys.exit(1)

    doc_id = poll_resp.json().get("reportDocumentId")

    # 3. Get Document Download URL
    doc_url = f"{endpoint}/reports/2021-06-30/documents/{doc_id}"
    doc_resp = requests.get(doc_url, headers=headers)
    doc_resp.raise_for_status()
    doc_info = doc_resp.json()
    download_url = doc_info.get("url")
    compression = doc_info.get("compressionAlgorithm")

    # 4. Download and Parse the TSV
    print("Downloading and parsing report...")
    dl_resp = requests.get(download_url)
    dl_resp.raise_for_status()
    
    content = dl_resp.content
    if compression == "GZIP":
        content = gzip.decompress(content)
        
    text = content.decode('utf-8', errors='replace')
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')

    bucket_totals = {
        "0-60": 0,
        "61-90": 0,
        "91-180": 0,
        "181+": 0
    }

    def safe_int(val):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    report_date = date.today().isoformat()
    records = []

    for row in reader:
        sku = row.get('sku')
        if not sku:
            continue
            
        # 0-60 is (0-30) + (31-60)
        age_0_60 = safe_int(row.get('inv-age-0-to-30-days', 0)) + safe_int(row.get('inv-age-31-to-60-days', 0))
        # 61-90
        age_61_90 = safe_int(row.get('inv-age-61-to-90-days', 0))
        # 91-180
        age_91_180 = safe_int(row.get('inv-age-91-to-180-days', 0))
        # 181+ is (181-270) + (271-365) + (365+)
        age_181_plus = safe_int(row.get('inv-age-181-to-270-days', 0)) + safe_int(row.get('inv-age-271-to-365-days', 0)) + safe_int(row.get('inv-age-365-plus-days', 0))

        if age_0_60 > 0:
            records.append({"report_date": report_date, "account_id": account_id, "sku": sku, "bucket": "0-60", "item_count": age_0_60})
        if age_61_90 > 0:
            records.append({"report_date": report_date, "account_id": account_id, "sku": sku, "bucket": "61-90", "item_count": age_61_90})
        if age_91_180 > 0:
            records.append({"report_date": report_date, "account_id": account_id, "sku": sku, "bucket": "91-180", "item_count": age_91_180})
        if age_181_plus > 0:
            records.append({"report_date": report_date, "account_id": account_id, "sku": sku, "bucket": "181+", "item_count": age_181_plus})

    print(f"Deleting existing records for account {account_id} on {report_date} to prevent double counting...")
    supabase.table("inventory_age").delete().eq("account_id", account_id).eq("report_date", report_date).execute()

    print(f"Inserting {len(records)} records into Supabase...")
    
    # Chunk inserts to avoid payload limits
    chunk_size = 1000
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        response = supabase.table("inventory_age").insert(chunk).execute()
        
    print(f"Successfully inserted SKU-level inventory age rows for {report_date}")

if __name__ == "__main__":
    main()
