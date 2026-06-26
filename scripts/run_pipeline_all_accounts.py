#!/usr/bin/env python3
"""
Saddle Multi-Account SP-API Daily Pipeline
==========================================
Professional SaaS pattern: gap-detection + rate-limited Data Kiosk submission
+ parallel FBA/BSR.

Architecture
------------
1. Gap Detection     — Query the DB for which (account, date) pairs are missing
                       from sc_raw.sales_traffic. Only request what's absent.
2. Data Kiosk        — Rate-limited (1 createQuery / 60s across all accounts).
                       Submits one query at a time, polls to completion.
3. FBA + BSR         — No rate limits. Run concurrently across all accounts
                       using a thread pool.

Scaling characteristics
-----------------------
  3  accounts  → ~5–10 min/day (current)
  20 accounts  → ~25–30 min/day (fine for a single cron)
  50 accounts  → ~55–60 min/day (fine, stays under 90m Railway timeout)
  100 accounts → ~105 min/day  → migrate Data Kiosk to async queue pattern
                                  (same pattern as ads.report_queue)

Usage
-----
    python3 scripts/run_pipeline_all_accounts.py             # gap-fill yesterday + up to 30d back
    python3 scripts/run_pipeline_all_accounts.py 2026-03-24  # explicit single date, all accounts
    python3 scripts/run_pipeline_all_accounts.py --account s2c_uae_test  # one account only
"""

from __future__ import annotations

import logging
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("saddl.spapi_daily")

DATA_KIOSK_RATE_LIMIT_SECS = 62   # Amazon: 1 createQuery / 60s per app (62 for safety)
LOOKBACK_DAYS               = 30   # How far back to check for gaps
MAX_FBA_BSR_WORKERS         = 8    # Parallel threads for FBA + BSR


# ── DB ────────────────────────────────────────────────────────────────────────

def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        sys.exit("❌  DATABASE_URL is not set.")
    return url


def _fetch_active_accounts(client_id_filter: str | None = None) -> list[dict]:
    import psycopg2
    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT client_id, lwa_refresh_token, marketplace_id, region_endpoint
                FROM client_settings
                WHERE onboarding_status = 'active'
                  AND lwa_refresh_token IS NOT NULL
            """
            params: list = []
            if client_id_filter:
                sql += " AND client_id = %s"
                params.append(client_id_filter)
            sql += " ORDER BY client_id"
            cur.execute(sql, params)
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


# ── Gap Detector ──────────────────────────────────────────────────────────────

def _find_missing_dates(client_id: str, lookback_days: int = LOOKBACK_DAYS) -> list[str]:
    """
    Return dates in the last `lookback_days` that have no rows in
    sc_raw.sales_traffic for this account. Ordered oldest-first so
    we backfill chronologically.
    """
    import psycopg2
    today = date.today()
    window_start = today - timedelta(days=lookback_days)
    yesterday = today - timedelta(days=1)

    with psycopg2.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT report_date::date
                FROM sc_raw.sales_traffic
                WHERE account_id = %s
                  AND report_date >= %s
                  AND report_date <= %s
            """, (client_id, window_start, yesterday))
            have = {r[0] for r in cur.fetchall()}

    all_dates = set()
    d = window_start
    while d <= yesterday:
        all_dates.add(d)
        d += timedelta(days=1)

    missing = sorted(all_dates - have)   # oldest first
    return [d.isoformat() for d in missing]


# ── Data Kiosk (rate-limited, sequential) ─────────────────────────────────────

def _run_data_kiosk_for_account(account: dict, dates: list[str]) -> dict:
    """
    Submit one Data Kiosk query per missing date for this account.
    Rate limiting is the caller's responsibility — this function submits
    immediately and the caller inserts the 62-second gap between calls.
    Returns {date: rows_written} for successful dates.
    """
    client_id       = account["client_id"]
    refresh_token   = account["refresh_token"]
    marketplace_id  = account["marketplace_id"]
    region_endpoint = account["region_endpoint"]

    prev_token = os.environ.get("LWA_REFRESH_TOKEN_UAE")
    os.environ["LWA_REFRESH_TOKEN_UAE"] = refresh_token

    results: dict[str, int] = {}
    errors:  list[str]      = []

    try:
        # Flush cached token
        try:
            from pipelines import sp_api_client as _spc
            _spc._token_cache.update({"access_token": None, "expires_at": None})
        except Exception:
            pass

        from pipelines.sp_api_client import get_settings, get_token
        from pipelines.spapi_pipeline import (
            build_sales_traffic_query, create_data_kiosk_query,
            poll_query_status, download_query_document, upsert_sales_traffic,
        )
        from pipeline.aggregator import upsert_account_daily, upsert_osi_index

        prev_mkt = os.environ.get("MARKETPLACE_ID_UAE")
        prev_ep  = os.environ.get("SP_API_ENDPOINT")
        os.environ["MARKETPLACE_ID_UAE"] = marketplace_id
        if region_endpoint:
            os.environ["SP_API_ENDPOINT"] = (
                f"https://{region_endpoint}"
                if not region_endpoint.startswith("http")
                else region_endpoint
            )

        settings     = get_settings()
        access_token = get_token(force_refresh=True)

        os.environ["MARKETPLACE_ID_UAE"] = prev_mkt or marketplace_id
        if prev_ep is not None:
            os.environ["SP_API_ENDPOINT"] = prev_ep
        else:
            os.environ.pop("SP_API_ENDPOINT", None)

        db_url = _db_url()

        # One query per missing date (caller rate-limits between accounts/dates)
        for t_date in dates:
            try:
                log.info("  [%s] Data Kiosk → %s", client_id, t_date)
                qbody   = build_sales_traffic_query(t_date, t_date, settings.marketplace_id)
                qid     = create_data_kiosk_query(access_token, qbody, region_endpoint=region_endpoint)

                payload = poll_query_status(
                    access_token, qid,
                    poll_seconds=15,      # poll every 15s (most queries resolve in <3 min)
                    max_wait_minutes=20,  # give up after 20 min (was 45 — overly conservative)
                    region_endpoint=region_endpoint,
                )
                doc_id = payload.get("dataDocumentId")
                if doc_id:
                    records = download_query_document(access_token, doc_id, region_endpoint=region_endpoint)
                    rows    = upsert_sales_traffic(records, t_date, settings.marketplace_id, account_id=client_id)
                    results[t_date] = rows
                    log.info("  [%s] ✓ %s → %d rows", client_id, t_date, rows)

                    # Aggregate immediately after ingest
                    try:
                        upsert_account_daily(db_url, t_date, settings.marketplace_id,
                                             client_id=client_id, account_id=client_id)
                        upsert_osi_index(db_url, t_date, settings.marketplace_id, account_id=client_id)
                    except Exception as agg_exc:
                        log.warning("  [%s] Aggregation failed for %s: %s", client_id, t_date, agg_exc)
                else:
                    log.warning("  [%s] No dataDocumentId for %s — skipping", client_id, t_date)

            except Exception as date_exc:
                log.warning("  [%s] Failed %s: %s", client_id, t_date, date_exc)
                errors.append(f"{t_date}: {date_exc}")

    except Exception as auth_exc:
        log.error("  [%s] Auth/setup failed: %s", client_id, auth_exc)
        errors.append(str(auth_exc))
    finally:
        if prev_token is not None:
            os.environ["LWA_REFRESH_TOKEN_UAE"] = prev_token
        else:
            os.environ.pop("LWA_REFRESH_TOKEN_UAE", None)
        try:
            from pipelines import sp_api_client as _spc
            _spc._token_cache.update({"access_token": None, "expires_at": None})
        except Exception:
            pass

    return {"client_id": client_id, "results": results, "errors": errors}


# ── FBA + BSR (parallel, no rate limits) ─────────────────────────────────────

def _run_fba(account: dict) -> int:
    """Pull FBA inventory for one account. Thread-safe."""
    from pipelines.spapi_pipeline import pull_fba_inventory
    try:
        return pull_fba_inventory(
            account["client_id"],
            marketplace_id=account["marketplace_id"],
            region_endpoint=account["region_endpoint"],
            lwa_refresh_token=account["refresh_token"],
        ) or 0
    except Exception as exc:
        log.warning("  [%s] FBA failed: %s", account["client_id"], exc)
        return 0


def _run_bsr(account: dict, report_date: str) -> int:
    """Pull BSR for latest ASINs. Thread-safe, best-effort."""
    import psycopg2
    from pipeline.bsr_pipeline import fetch_bsr_batch, upsert_bsr_history
    client_id = account["client_id"]
    try:
        with psycopg2.connect(_db_url()) as conn:
            with conn.cursor() as cur:
                # Only look at the last 30 days to avoid pulling stale ASINs
                cur.execute("""
                    SELECT DISTINCT child_asin
                    FROM sc_raw.sales_traffic
                    WHERE marketplace_id = %s AND account_id = %s
                      AND report_date >= CURRENT_DATE - 30
                      AND child_asin IS NOT NULL
                    LIMIT 500
                """, (account["marketplace_id"], client_id))
                asins = [r[0] for r in cur.fetchall()]

        if not asins:
            return 0

        # Exchange refresh token dynamically and thread-safely (bypassing global cache)
        lwa_client_id     = os.getenv("LWA_CLIENT_ID", "")
        lwa_client_secret = os.getenv("LWA_CLIENT_SECRET", "")
        region_endpoint   = account["region_endpoint"]

        token_resp = requests.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": account["refresh_token"],
                "client_id": lwa_client_id,
                "client_secret": lwa_client_secret,
            }
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        cfg = {
            "lwa_client_id":     lwa_client_id,
            "lwa_client_secret": lwa_client_secret,
            "refresh_token":     account["refresh_token"],
            "aws_access_key":    os.getenv("AWS_ACCESS_KEY_ID", ""),
            "aws_secret_key":    os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "aws_region":        os.getenv("AWS_REGION", "eu-west-1"),
            "marketplace_id":    account["marketplace_id"],
            "spapi_account_id":  client_id,
            "endpoint":          f"https://{region_endpoint}" if not region_endpoint.startswith("http") else region_endpoint,
            "database_url":      _db_url(),
        }
        
        bsr_rows = fetch_bsr_batch(cfg, token=token, asins=asins, report_date=report_date)
        return upsert_bsr_history(bsr_rows, _db_url())
    except Exception as exc:
        log.warning("  [%s] BSR failed: %s", client_id, exc)
        return 0


def _run_inventory_age(account: dict) -> int:
    """Pull FBA Inventory Planning Data (Aged Inventory) for one account. Thread-safe."""
    import time
    import gzip
    import csv
    import io
    import requests
    import psycopg2
    from psycopg2.extras import execute_values
    from datetime import date

    client_id = account["client_id"]
    try:
        # Generate the SP-API token dynamically and thread-safely (bypassing global cache)
        lwa_client_id     = os.getenv("LWA_CLIENT_ID", "")
        lwa_client_secret = os.getenv("LWA_CLIENT_SECRET", "")
        region_endpoint   = account["region_endpoint"]
        
        token_resp = requests.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": account["refresh_token"],
                "client_id": lwa_client_id,
                "client_secret": lwa_client_secret,
            }
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]
        
        endpoint = f"https://{region_endpoint}" if not region_endpoint.startswith("http") else region_endpoint
        headers = {
            "x-amz-access-token": token,
            "Content-Type": "application/json"
        }

        # 1. Request Report
        create_url = f"{endpoint}/reports/2021-06-30/reports"
        payload = {
            "reportType": "GET_FBA_INVENTORY_PLANNING_DATA",
            "marketplaceIds": [account["marketplace_id"]]
        }
        resp = requests.post(create_url, headers=headers, json=payload)
        resp.raise_for_status()
        report_id = resp.json().get("reportId")

        # 2. Poll Status
        while True:
            poll_resp = requests.get(f"{endpoint}/reports/2021-06-30/reports/{report_id}", headers=headers)
            poll_resp.raise_for_status()
            status = poll_resp.json().get("processingStatus")
            if status in ["DONE", "CANCELLED", "FATAL"]:
                break
            time.sleep(15)

        if status != "DONE":
            log.warning("  [%s] Inventory Age failed with status: %s", client_id, status)
            return 0

        # 3. Get Document Download URL
        doc_id = poll_resp.json().get("reportDocumentId")
        doc_resp = requests.get(f"{endpoint}/reports/2021-06-30/documents/{doc_id}", headers=headers)
        doc_resp.raise_for_status()
        doc_info = doc_resp.json()
        download_url = doc_info.get("url")
        compression = doc_info.get("compressionAlgorithm")

        # 4. Download and Parse
        dl_resp = requests.get(download_url)
        dl_resp.raise_for_status()
        content = dl_resp.content
        if compression == "GZIP":
            content = gzip.decompress(content)
            
        text = content.decode('utf-8', errors='replace')
        reader = csv.DictReader(io.StringIO(text), delimiter='\t')

        def safe_int(val):
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return 0

        records = []
        report_date = date.today().isoformat()

        for row in reader:
            sku = row.get('sku')
            if not sku:
                continue
                
            age_0_60 = safe_int(row.get('inv-age-0-to-30-days', 0)) + safe_int(row.get('inv-age-31-to-60-days', 0))
            age_61_90 = safe_int(row.get('inv-age-61-to-90-days', 0))
            age_91_180 = safe_int(row.get('inv-age-91-to-180-days', 0))
            age_181_plus = safe_int(row.get('inv-age-181-to-270-days', 0)) + safe_int(row.get('inv-age-271-to-365-days', 0)) + safe_int(row.get('inv-age-365-plus-days', 0))

            if age_0_60 > 0:
                records.append((report_date, client_id, sku, "0-60", age_0_60))
            if age_61_90 > 0:
                records.append((report_date, client_id, sku, "61-90", age_61_90))
            if age_91_180 > 0:
                records.append((report_date, client_id, sku, "91-180", age_91_180))
            if age_181_plus > 0:
                records.append((report_date, client_id, sku, "181+", age_181_plus))

        if not records:
            return 0

        # 5. Replace DB snapshot for this date/account to ensure idempotency and prevent duplicates
        with psycopg2.connect(_db_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.inventory_age WHERE account_id = %s AND report_date = %s",
                    (client_id, report_date)
                )
                query = """
                    INSERT INTO public.inventory_age (report_date, account_id, sku, bucket, item_count)
                    VALUES %s
                """
                execute_values(cur, query, records, page_size=1000)
                
        return len(records)

    except Exception as exc:
        log.warning("  [%s] Inventory Age failed: %s", client_id, exc)
        return 0


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Saddle SP-API daily pipeline")
    parser.add_argument("date", nargs="?",
                        help="Optional explicit date (YYYY-MM-DD). Default: gap-fill last 30 days.")
    parser.add_argument("--account", help="Run for a single account only.")
    args = parser.parse_args()

    log.info("═══════════════════════════════════════════════════════════")
    log.info("  Saddle SP-API Daily Pipeline")
    log.info("  Mode : %s", f"explicit date {args.date}" if args.date else "gap-detection (last 30d)")
    log.info("═══════════════════════════════════════════════════════════")

    accounts = _fetch_active_accounts(client_id_filter=args.account)
    if not accounts:
        log.warning("No active accounts found — nothing to do.")
        sys.exit(0)

    log.info("Accounts (%d): %s", len(accounts), ", ".join(a["client_id"] for a in accounts))

    # ── Phase 1: Data Kiosk (rate-limited, sequential across all accounts) ─────
    # Rate limit: 1 createQuery per 62s ACROSS ALL ACCOUNTS sharing the same LWA app.
    # We maintain a single global submission timer.
    log.info("")
    log.info("── Phase 1/2: Data Kiosk (Sales & Traffic) ─────────────────")

    last_submit_ts: float = 0.0
    all_dk_results: list[dict] = []

    # Build work list: (account, [missing_dates]) per account
    work: list[tuple[dict, list[str]]] = []
    for account in accounts:
        if args.date:
            dates = [args.date]    # explicit override
        else:
            dates = _find_missing_dates(account["client_id"])
            
            # --- Fix 1: Force re-pulls for recent dates to handle Amazon session lag ---
            # Amazon traffic data (sessions) is delayed 48-72h. We force D-2, D-3, D-7
            # so that initially-zeroed rows in DB are eventually overwritten with real data.
            today = date.today()
            force_days = [2, 3, 7]
            force_iso  = [(today - timedelta(days=d)).isoformat() for d in force_days]
            
            # Combine, deduplicate, and sort
            merged = set(dates) | set(force_iso)
            # Only keep dates within the last 30 days (safety)
            window_start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
            dates = sorted([d for d in merged if d >= window_start and d < today.isoformat()])
            # --------------------------------------------------------------------------

        log.info("  [%s] %d date(s) to fetch%s", account["client_id"],
                 len(dates), " — nothing to pull" if not dates else f": {dates[:3]}{'…' if len(dates) > 3 else ''}")
        if dates:
            work.append((account, dates))

    if not work:
        log.info("  All accounts up to date. Skipping Data Kiosk.")
    else:
        total_queries = sum(len(dates) for _, dates in work)
        est_min = (total_queries * DATA_KIOSK_RATE_LIMIT_SECS) // 60
        log.info("  %d total queries to submit (~%d min at rate limit)", total_queries, est_min)

        for account, dates in work:
            for t_date in dates:
                # Global rate limit gate
                elapsed = time.monotonic() - last_submit_ts
                if elapsed < DATA_KIOSK_RATE_LIMIT_SECS and last_submit_ts > 0:
                    wait = DATA_KIOSK_RATE_LIMIT_SECS - elapsed
                    log.info("  Rate limit: waiting %.1fs before next query…", wait)
                    time.sleep(wait)

                result = _run_data_kiosk_for_account(account, [t_date])
                last_submit_ts = time.monotonic()
                all_dk_results.append(result)

    # ── Phase 2: FBA + BSR (parallel, no rate limits) ─────────────────────────
    log.info("")
    log.info("── Phase 2/2: FBA Inventory + BSR (parallel) ────────────────")
    today_str = date.today().isoformat()

    fba_totals: dict[str, int] = {}
    bsr_totals: dict[str, int] = {}
    inv_age_totals: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=min(MAX_FBA_BSR_WORKERS, len(accounts))) as pool:
        fba_futures = {pool.submit(_run_fba, a): a["client_id"] for a in accounts}
        bsr_futures = {pool.submit(_run_bsr, a, today_str): a["client_id"] for a in accounts}
        
        # Add Inventory Age to the parallel pool
        inv_age_futures = {pool.submit(_run_inventory_age, a): a["client_id"] for a in accounts}

        for f in as_completed(fba_futures):
            cid = fba_futures[f]
            rows = f.result()
            fba_totals[cid] = rows
            log.info("  [%s] FBA → %d rows", cid, rows)

        for f in as_completed(bsr_futures):
            cid = bsr_futures[f]
            rows = f.result()
            bsr_totals[cid] = rows
            if rows:
                log.info("  [%s] BSR → %d rows", cid, rows)
                
        # Resolve Inventory Age
        for f in as_completed(inv_age_futures):
            cid = inv_age_futures[f]
            rows = f.result()
            inv_age_totals[cid] = rows
            if rows:
                log.info("  [%s] INV_AGE → %d rows", cid, rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("")
    log.info("═══════════════════════════════════════════════════════════")
    log.info("  SUMMARY")
    log.info("═══════════════════════════════════════════════════════════")
    for account in accounts:
        cid = account["client_id"]
        dk_result = next((r for r in all_dk_results if r["client_id"] == cid), None)
        sales_rows = sum(dk_result["results"].values()) if dk_result else 0
        errors     = dk_result["errors"] if dk_result else []
        status     = "✅" if not errors else "⚠️ "
        log.info("  %s %-22s  sales=%d  fba=%d  bsr=%d  inv_age=%d%s",
                 status, cid, sales_rows, fba_totals.get(cid, 0), bsr_totals.get(cid, 0), inv_age_totals.get(cid, 0),
                 f"  ERR={errors}" if errors else "")
    log.info("═══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
