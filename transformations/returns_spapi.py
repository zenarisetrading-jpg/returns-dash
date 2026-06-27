#!/usr/bin/env python3
import os
import sys
import time
import requests
import gzip
from datetime import datetime
from supabase import create_client, Client

def main():
    token = os.getenv("SP_API_TOKEN")
    endpoint = os.getenv("SP_API_ENDPOINT")
    account_id = os.getenv("ACCOUNT_ID")
    start_date = os.getenv("START_DATE")
    end_date = os.getenv("END_DATE")
    marketplace_id = os.getenv("MARKETPLACE_ID_UAE", "A2VIGQ35RCS4UG")
    
    if not all([token, endpoint, account_id, start_date, end_date]):
        print("Missing required environment variables (SP_API_TOKEN, SP_API_ENDPOINT, ACCOUNT_ID, START_DATE, END_DATE)", file=sys.stderr)
        sys.exit(1)

    supabase_url = os.getenv("REACT_APP_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("REACT_APP_SUPABASE_ANON_KEY")
    supabase: Client = create_client(supabase_url, supabase_key)

    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json"
    }

    # Format dates to ISO 8601
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00Z")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")
    except ValueError:
        print("Invalid date format. Expected YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    print(f"[{account_id}] Requesting FBA Returns Report from {start_date} to {end_date}...")
    create_url = f"{endpoint}/reports/2021-06-30/reports"
    payload = {
        "reportType": "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA",
        "dataStartTime": dt_start,
        "dataEndTime": dt_end,
        "marketplaceIds": [marketplace_id]
    }

    resp = requests.post(create_url, headers=headers, json=payload)
    if resp.status_code != 202:
        print(f"Failed to create report: {resp.status_code} - {resp.text}", file=sys.stderr)
        sys.exit(1)
        
    report_id = resp.json().get("reportId")
    print(f"Report ID: {report_id}")

    print("Waiting for report to generate...")
    max_retries = 30
    for _ in range(max_retries):
        poll_url = f"{endpoint}/reports/2021-06-30/reports/{report_id}"
        poll_resp = requests.get(poll_url, headers=headers)
        poll_resp.raise_for_status()
        status = poll_resp.json().get("processingStatus")
        
        if status in ["DONE", "CANCELLED", "FATAL"]:
            break
        time.sleep(15)

    if status != "DONE":
        print(f"Report generation failed with status: {status}", file=sys.stderr)
        sys.exit(1)

    print("Downloading report document...")
    doc_id = poll_resp.json().get("reportDocumentId")
    doc_url = f"{endpoint}/reports/2021-06-30/documents/{doc_id}"
    doc_resp = requests.get(doc_url, headers=headers)
    doc_resp.raise_for_status()
    doc_info = doc_resp.json()
    
    download_url = doc_info.get("url")
    compression = doc_info.get("compressionAlgorithm")

    dl_resp = requests.get(download_url)
    dl_resp.raise_for_status()
    
    content = dl_resp.content
    if compression == "GZIP":
        content = gzip.decompress(content)

    print("Uploading TSV to Supabase ingestion-raw bucket...")
    file_path = f"{account_id}/FBA_RETURNS_{start_date}_to_{end_date}.tsv"
    
    try:
        supabase.storage.from_("ingestion-raw").remove([file_path])
        supabase.storage.from_("ingestion-raw").upload(
            file_path, 
            content,
            file_options={"content-type": "text/tab-separated-values"}
        )
        print(f"Successfully uploaded {file_path}")
    except Exception as e:
        print(f"Failed to upload to Supabase: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
