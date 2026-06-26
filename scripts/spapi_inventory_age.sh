#!/usr/bin/env bash

# spapi_inventory_age.sh
# Fetch inventory age report from SP‑API and upsert into Supabase

set -euo pipefail

# Ensure required env vars are present (SP_API_TOKEN, SP_API_ENDPOINT, ACCOUNT_ID, etc.)
: "${SP_API_TOKEN:?Missing SP_API_TOKEN}"
: "${SP_API_ENDPOINT:?Missing SP_API_ENDPOINT}"
: "${ACCOUNT_ID:?Missing ACCOUNT_ID}"

# Run transformer to trigger SP-API report workflow and upsert to Supabase
echo "Starting inventory age report workflow for account: $ACCOUNT_ID..."
python3 $(dirname "$0")/../transformations/inventory_age.py

echo "Inventory age workflow completed successfully."
