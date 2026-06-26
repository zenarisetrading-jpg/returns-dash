#!/usr/bin/env python3
import os
import sys
import time
import requests
import gzip
import csv
import io

def main():
    token = os.getenv("SP_API_TOKEN")
    endpoint = os.getenv("SP_API_ENDPOINT")
    if not token or not endpoint:
        print("Missing SP_API_TOKEN or SP_API_ENDPOINT", file=sys.stderr)
        sys.exit(1)
        
    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json"
    }

    # 1. Create Report
    print("Requesting report...")
    create_url = f"{endpoint}/reports/2021-06-30/reports"
    payload = {
        "reportType": "GET_FBA_INVENTORY_PLANNING_DATA",
        "marketplaceIds": ["A2VIGQ35RCS4UG"]
    }
    resp = requests.post(create_url, headers=headers, json=payload)
    resp.raise_for_status()
    report_id = resp.json().get("reportId")
    print(f"Report ID: {report_id}")

    # 2. Poll Report
    while True:
        poll_url = f"{endpoint}/reports/2021-06-30/reports/{report_id}"
        poll_resp = requests.get(poll_url, headers=headers)
        poll_resp.raise_for_status()
        status = poll_resp.json().get("processingStatus")
        print(f"Status: {status}")
        if status in ["DONE", "CANCELLED", "FATAL"]:
            break
        time.sleep(10)

    if status != "DONE":
        print("Report failed.")
        sys.exit(1)

    doc_id = poll_resp.json().get("reportDocumentId")
    print(f"Document ID: {doc_id}")

    # 3. Get Document
    doc_url = f"{endpoint}/reports/2021-06-30/documents/{doc_id}"
    doc_resp = requests.get(doc_url, headers=headers)
    doc_resp.raise_for_status()
    doc_info = doc_resp.json()
    download_url = doc_info.get("url")
    compression = doc_info.get("compressionAlgorithm")

    # 4. Download
    print("Downloading document...")
    dl_resp = requests.get(download_url)
    dl_resp.raise_for_status()
    
    content = dl_resp.content
    if compression == "GZIP":
        content = gzip.decompress(content)
        
    text = content.decode('utf-8', errors='replace')
    reader = csv.reader(io.StringIO(text), delimiter='\t')
    headers_row = next(reader)
    print("Headers:", headers_row)
    
    with open("/tmp/test_report.tsv", "w") as f:
        f.write(text)

if __name__ == "__main__":
    main()
