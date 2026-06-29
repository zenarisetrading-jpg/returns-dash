#!/usr/bin/env python3
import os
import sys
import time
import requests
import hashlib
import psycopg2
from datetime import datetime

def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

def extract_amount_and_currency(charge_list, sub_string):
    amount = 0.0
    currency = None
    for charge in charge_list:
        charge_type = charge.get("ChargeType", "")
        if sub_string.lower() in charge_type.lower():
            val = charge.get("ChargeAmount", {})
            amount += safe_float(val.get("CurrencyAmount", 0.0))
            currency = val.get("CurrencyCode", currency)
    return amount if amount != 0.0 else None, currency

def extract_fee_and_currency(fee_list, sub_string):
    amount = 0.0
    currency = None
    matched_fees = []
    for fee in fee_list:
        fee_type = fee.get("FeeType", "")
        if sub_string.lower() in fee_type.lower():
            val = fee.get("FeeAmount", {})
            amount += safe_float(val.get("CurrencyAmount", 0.0))
            currency = val.get("CurrencyCode", currency)
            matched_fees.append(fee)
    return amount if amount != 0.0 else None, currency, matched_fees

def extract_other_fee_and_currency(fee_list, matched_fees):
    amount = 0.0
    currency = None
    for fee in fee_list:
        if fee not in matched_fees:
            val = fee.get("FeeAmount", {})
            amount += safe_float(val.get("CurrencyAmount", 0.0))
            currency = val.get("CurrencyCode", currency)
    return amount if amount != 0.0 else None, currency

def extract_promotion_and_currency(promotion_list):
    amount = 0.0
    currency = None
    for promo in promotion_list:
        val = promo.get("PromotionAmount", {})
        amount += safe_float(val.get("CurrencyAmount", 0.0))
        currency = val.get("CurrencyCode", currency)
    return amount if amount != 0.0 else None, currency

def ingest_financial_events(conn, account_id, events_payload):
    default_marketplace_id = os.getenv("MARKETPLACE_ID") or os.getenv("MARKETPLACE_ID_UAE") or "A2VIGQ35RCS4UG"
    with conn.cursor() as cur:
        # 1. Process Shipment Events
        shipment_events = events_payload.get("ShipmentEventList", [])
        print(f"  Processing {len(shipment_events)} shipment events...")
        for event in shipment_events:
            order_id = event.get("AmazonOrderId")
            marketplace_id = event.get("MarketplaceId") or default_marketplace_id
            posted_date = event.get("PostedDate")
            
            for item in event.get("ShipmentItemList", []):
                sku = item.get("SellerSKU")
                asin = item.get("ASIN")
                
                # Extract Charges
                charge_list = item.get("ItemChargeList", [])
                principal, p_curr = extract_amount_and_currency(charge_list, "Principal")
                tax, t_curr = extract_amount_and_currency(charge_list, "Tax")
                shipping, s_curr = extract_amount_and_currency(charge_list, "Shipping")
                
                # Extract Fees
                fee_list = item.get("ItemFeeList", [])
                fee_referral, r_curr, matched_r = extract_fee_and_currency(fee_list, "Referral")
                fee_fba, f_curr, matched_f = extract_fee_and_currency(fee_list, "FBA")
                fee_other, o_curr = extract_other_fee_and_currency(fee_list, matched_r + matched_f)
                
                # Extract Promotions
                promotion_amount, promo_curr = extract_promotion_and_currency(item.get("PromotionList", []))
                
                cur.execute("""
                    INSERT INTO finance.shipment_events (
                        client_id, marketplace_id, order_id, asin, sku,
                        principal, principal_currency, tax, tax_currency,
                        shipping, shipping_currency, fee_referral, fee_referral_currency,
                        fee_fba, fee_fba_currency, fee_other, fee_other_currency,
                        promotion_amount, promotion_currency, posted_date, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    ) ON CONFLICT DO NOTHING
                """, (
                    account_id, marketplace_id, order_id, asin, sku,
                    principal, p_curr or "AED", tax, t_curr or "AED",
                    shipping, s_curr or "AED", fee_referral, r_curr or "AED",
                    fee_fba, f_curr or "AED", fee_other, o_curr or "AED",
                    promotion_amount, promo_curr or "AED", posted_date
                ))

        # 2. Process Refund Events
        refund_events = events_payload.get("RefundEventList", [])
        print(f"  Processing {len(refund_events)} refund events...")
        for event in refund_events:
            order_id = event.get("AmazonOrderId")
            marketplace_id = event.get("MarketplaceId") or default_marketplace_id
            posted_date = event.get("PostedDate")
            
            for item in event.get("ShipmentItemRefundList", []):
                sku = item.get("SellerSKU")
                asin = item.get("ASIN")
                
                charge_list = item.get("ItemChargeRefundList", [])
                refund_principal, rp_curr = extract_amount_and_currency(charge_list, "Principal")
                refund_tax, rt_curr = extract_amount_and_currency(charge_list, "Tax")
                refund_shipping, rs_curr = extract_amount_and_currency(charge_list, "Shipping")
                
                fee_list = item.get("ItemFeeRefundList", [])
                fee_reversal, fr_curr, _ = extract_fee_and_currency(fee_list, "Referral")
                if not fee_reversal:
                    fee_reversal, fr_curr, _ = extract_fee_and_currency(fee_list, "Commission")
                
                cur.execute("""
                    INSERT INTO finance.refund_events (
                        client_id, marketplace_id, order_id, asin, sku,
                        refund_principal, refund_principal_currency,
                        refund_tax, refund_tax_currency,
                        refund_shipping, refund_shipping_currency,
                        fee_reversal, fee_reversal_currency, posted_date, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    ) ON CONFLICT DO NOTHING
                """, (
                    account_id, marketplace_id, order_id, asin, sku,
                    refund_principal, rp_curr or "AED", refund_tax, rt_curr or "AED",
                    refund_shipping, rs_curr or "AED", fee_reversal, fr_curr or "AED", posted_date
                ))

        # 3. Process Service Fee Events (Fee Events)
        service_fee_events = events_payload.get("ServiceFeeEventList", [])
        print(f"  Processing {len(service_fee_events)} service fee events...")
        for event in service_fee_events:
            posted_date = event.get("PostedDate") or datetime.utcnow().isoformat()
            event_type = event.get("FeeDescription") or "ServiceFee"
            marketplace_id = event.get("MarketplaceId") or default_marketplace_id
            
            for fee in event.get("FeeList", []):
                fee_type = fee.get("FeeType")
                val = fee.get("FeeAmount", {})
                amount = safe_float(val.get("CurrencyAmount", 0.0))
                currency = val.get("CurrencyCode", "AED")
                
                # Generate unique hash for deduplication
                unique_str = f"{posted_date}_{fee_type}_{amount}_{account_id}"
                event_hash = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
                
                cur.execute("""
                    INSERT INTO finance.fee_events (
                        client_id, marketplace_id, event_type, fee_type, amount, currency, posted_date, event_hash, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    ) ON CONFLICT (event_hash) DO NOTHING
                """, (
                    account_id, marketplace_id, event_type, fee_type, amount, currency, posted_date, event_hash
                ))

        # 4. Process Adjustment Events
        adjustment_events = events_payload.get("AdjustmentEventList", [])
        print(f"  Processing {len(adjustment_events)} adjustment events...")
        for event in adjustment_events:
            adjustment_type = event.get("AdjustmentType")
            posted_date = event.get("PostedDate")
            marketplace_id = event.get("MarketplaceId") or default_marketplace_id
            
            for item in event.get("AdjustmentItemList", []):
                sku = item.get("SellerSKU")
                asin = item.get("ASIN")
                val = item.get("TotalAmount", {})
                amount = safe_float(val.get("CurrencyAmount", 0.0))
                currency = val.get("CurrencyCode", "AED")
                
                unique_str = f"{posted_date}_{sku}_{adjustment_type}_{amount}_{account_id}"
                event_hash = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
                
                cur.execute("""
                    INSERT INTO finance.adjustment_events (
                        client_id, marketplace_id, adjustment_type, asin, sku, amount, currency, posted_date, event_hash, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    ) ON CONFLICT (event_hash) DO NOTHING
                """, (
                    account_id, marketplace_id, adjustment_type, asin, sku, amount, currency, posted_date, event_hash
                ))

def main():
    token = os.getenv("SP_API_TOKEN")
    endpoint = os.getenv("SP_API_ENDPOINT")
    account_id = os.getenv("ACCOUNT_ID")
    start_date = os.getenv("START_DATE")
    end_date = os.getenv("END_DATE")
    
    if not all([token, endpoint, account_id, start_date, end_date]):
        print("Missing required environment variables (SP_API_TOKEN, SP_API_ENDPOINT, ACCOUNT_ID, START_DATE, END_DATE)", file=sys.stderr)
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json"
    }

    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00Z")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")
    except ValueError:
        print("Invalid date format. Expected YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    url = f"{endpoint}/finances/v0/financialEvents"
    params = {
        "PostedAfter": dt_start,
        "PostedBefore": dt_end,
        "MaxResultsPerPage": 100
    }

    conn = psycopg2.connect(db_url)
    try:
        page = 1
        while True:
            print(f"[{account_id}] Fetching Financial Events page {page} ({start_date} to {end_date})...")
            resp = requests.get(url, headers=headers, params=params)
            resp.raise_for_status()
            
            data = resp.json()
            payload = data.get("payload", {})
            financial_events = payload.get("FinancialEvents", {})
            
            ingest_financial_events(conn, account_id, financial_events)
            conn.commit()
            
            next_token = payload.get("NextToken")
            if not next_token:
                break
                
            params = {"NextToken": next_token}
            page += 1
            time.sleep(2) # Throttle to avoid rate limits
            
    except Exception as e:
        print(f"Error fetching or ingesting financial events: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
