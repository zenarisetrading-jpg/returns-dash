#!/usr/bin/env bash

# get_spapi_token.sh
# Generates a Selling Partner API (SP‑API) access token using the LWA refresh token.
# It prints the access token to stdout. You can capture it and export as SP_API_TOKEN.

# ---- Configuration ----
# You can set these values via environment variables before running the script,
# or edit the defaults below.
LWA_CLIENT_ID="${LWA_CLIENT_ID:-amzn1.application-oa2-client.01f9593238f1407788692c0bde4500b5}"
LWA_CLIENT_SECRET="${LWA_CLIENT_SECRET:-amzn1.oa2-cs.v1.c47c83dab582f8bc460b5bade13418476e83f07996588cc40b55570157b9fa3e}"

# Attempt to load an account-specific token if ACCOUNT_ID is provided
if [[ -n "$ACCOUNT_ID" ]]; then
  UPPER_ACCOUNT=$(echo "$ACCOUNT_ID" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
  VAR_NAME="LWA_REFRESH_TOKEN_${UPPER_ACCOUNT}"
  LWA_REFRESH_TOKEN="${!VAR_NAME}"
fi

# Fallback to the default UAE token if an account-specific one isn't found
if [[ -z "$LWA_REFRESH_TOKEN" ]]; then
  LWA_REFRESH_TOKEN="${LWA_REFRESH_TOKEN_UAE:-}"
fi
# Endpoint for the UAE marketplace (EU region)
SP_API_ENDPOINT="${SP_API_ENDPOINT:-https://sellingpartnerapi-eu.amazon.com}"

if [[ -z "$LWA_REFRESH_TOKEN" ]]; then
  echo "Error: LWA_REFRESH_TOKEN_UAE is not set. Export it or edit this script." >&2
  exit 1
fi

# Request an access token from Amazon LWA
RESPONSE=$(curl -s -X POST "https://api.amazon.com/auth/o2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=$LWA_REFRESH_TOKEN&client_id=$LWA_CLIENT_ID&client_secret=$LWA_CLIENT_SECRET")

# Extract the access_token (requires jq; fallback to simple grep if jq missing)
if command -v jq >/dev/null 2>&1; then
  ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
else
  ACCESS_TOKEN=$(echo "$RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
fi

if [[ -z "$ACCESS_TOKEN" || "$ACCESS_TOKEN" == "null" ]]; then
  echo "Failed to obtain access token. Response:" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# Print the token – you can capture it like: TOKEN=$(./scripts/get_spapi_token.sh)
printf "%s" "$ACCESS_TOKEN"
