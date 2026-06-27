import os
import json
import time
import requests
from supabase import create_client, Client
from datetime import datetime, timezone
import logging
from dotenv import load_dotenv
load_dotenv()
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)-13s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def _db_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials")
    return create_client(url, key)

def get_amazon_url(asin: str, marketplace: str = "AE") -> str:
    """Generate the Amazon reviews URL based on marketplace."""
    tld = "ae" if marketplace.upper() == "AE" else "sa"
    # Using the /product-reviews/ endpoint sorts by most recent
    return f"https://www.amazon.{tld}/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?sortBy=recent"

def scrape_with_firecrawl(asin: str, marketplace: str):
    """Tier 1: Use Firecrawl Extract to parse reviews directly into JSON."""
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        logging.warning("No FIRECRAWL_API_KEY found, skipping Firecrawl.")
        return None

    url = get_amazon_url(asin, marketplace)
    logging.info(f"    [FIRECRAWL] Attempting to scrape {url}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    schema = {
        "type": "object",
        "properties": {
            "star_rating": {"type": "number", "description": "Overall star rating out of 5"},
            "total_reviews": {"type": "number", "description": "Total number of global ratings/reviews"},
            "one_star_pct": {"type": "number", "description": "Percentage of 1 star reviews"},
            "two_star_pct": {"type": "number", "description": "Percentage of 2 star reviews"},
            "three_star_pct": {"type": "number", "description": "Percentage of 3 star reviews"},
            "four_star_pct": {"type": "number", "description": "Percentage of 4 star reviews"},
            "five_star_pct": {"type": "number", "description": "Percentage of 5 star reviews"},
            "reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "review_id": {"type": "string", "description": "Unique ID of the review if available, else a hash"},
                        "rating": {"type": "number", "description": "Star rating given by the user"},
                        "review_date": {"type": "string", "description": "Date of the review in YYYY-MM-DD format"},
                        "title": {"type": "string", "description": "Title of the review"},
                        "review_text": {"type": "string", "description": "Full text body of the review"},
                        "sentiment": {"type": "string", "description": "positive, neutral, or negative"}
                    },
                    "required": ["rating", "review_date", "title", "review_text", "sentiment"]
                }
            }
        },
        "required": ["star_rating", "total_reviews", "one_star_pct", "two_star_pct", "three_star_pct", "four_star_pct", "five_star_pct", "reviews"]
    }

    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {
            "schema": schema,
            "prompt": "Extract the overall product listing health (star ratings, percentages) and the list of individual recent customer reviews from this page."
        }
    }
    
    response = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and "extract" in data.get("data", {}):
            return data["data"]["extract"]
        else:
            logging.error(f"    [FIRECRAWL] Success but no extract data: {data}")
    else:
        logging.error(f"    [FIRECRAWL] Failed with status {response.status_code}: {response.text}")
    return None

def scrape_with_scrapergraph(asin: str, marketplace: str):
    """Tier 2: ScraperGraphAI Fallback"""
    sgai_key = os.environ.get("SGAI_API_KEY")
    if not sgai_key:
        logging.warning("No SGAI_API_KEY found, skipping ScraperGraph.")
        return None

    url = get_amazon_url(asin, marketplace)
    logging.info(f"    [SCRAPEGRAPH] Attempting to scrape {url}")
    
    headers = {
        "Content-Type": "application/json",
        "SGAI-APIKEY": sgai_key
    }
    
    payload = {
        "website_url": url,
        "user_prompt": "Extract the overall product listing health (star ratings, percentages) and the list of individual recent customer reviews.",
        "output_schema": {
            "star_rating": "Overall star rating out of 5",
            "total_reviews": "Total number of global ratings",
            "one_star_pct": "Percentage of 1 star reviews",
            "two_star_pct": "Percentage of 2 star reviews",
            "three_star_pct": "Percentage of 3 star reviews",
            "four_star_pct": "Percentage of 4 star reviews",
            "five_star_pct": "Percentage of 5 star reviews",
            "reviews": [
                {
                    "review_id": "Unique ID of the review",
                    "rating": "Star rating",
                    "review_date": "Date of the review",
                    "title": "Title of the review",
                    "review_text": "Full text body of the review",
                    "sentiment": "positive, neutral, or negative"
                }
            ]
        }
    }
    
    try:
        response = requests.post("https://api.scrapegraphai.com/v1/smartscraper", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # ScrapeGraphAI returns the result in data['result']
        if "result" in data:
            res = data["result"]
            if isinstance(res, str):
                res = json.loads(res)
            return res
        else:
            logging.error(f"    [SCRAPEGRAPH] No result in response: {data}")
    except Exception as e:
        logging.error(f"    [SCRAPEGRAPH] Exception occurred: {e}")
    
    return None

def run_reviews_scraper(asin: str, client_id: str, marketplace: str):
    """Main extraction logic running through the 3-Tier Fallback."""
    
    # 1. Firecrawl
    data = scrape_with_firecrawl(asin, marketplace)
    
    # 2. ScraperGraphAI (Fallback)
    if not data or not data.get("reviews"):
        logging.warning("    [!] Firecrawl failed or returned empty. Falling back to ScraperGraph.")
        data = scrape_with_scrapergraph(asin, marketplace)
        
    # 3. Final Check
    if not data or not data.get("reviews"):
        logging.error(f"    [X] All scraper tiers failed for ASIN {asin}")
        return False
        
    logging.info(f"    [SUCCESS] Scraped {len(data['reviews'])} reviews for {asin}")
    
    # Prepare Data for Upsert
    now = datetime.now(timezone.utc).isoformat()
    supabase = _db_client()
    
    # Upsert Health (only if we got valid health data from Firecrawl)
    if data.get("total_reviews", 0) > 0:
        health_payload = {
            "asin": asin,
            "client_id": client_id,
            "star_rating": data.get("star_rating", 0),
            "total_reviews": data.get("total_reviews", 0),
            "one_star_pct": data.get("one_star_pct", 0),
            "two_star_pct": data.get("two_star_pct", 0),
            "three_star_pct": data.get("three_star_pct", 0),
            "four_star_pct": data.get("four_star_pct", 0),
            "five_star_pct": data.get("five_star_pct", 0),
            "updated_at": now
        }
        try:
            # We use an ASIN + client_id constraint or just match to update
            # Since the table is returns.product_listing_health
            res = supabase.table("product_listing_health").upsert(health_payload, on_conflict="asin,client_id").execute()
        except Exception as e:
            logging.error(f"    [SUPABASE] Failed to upsert health: {e}")
            
    # Upsert Reviews
    review_payloads = []
    for r in data["reviews"]:
        # Generate a distinct review ID if none provided by the scraper
        rid = str(r.get("review_id", ""))
        if not rid or len(rid) < 5:
            import hashlib
            rid = hashlib.md5(f"{asin}{r.get('review_text')}".encode()).hexdigest()
            
        review_payloads.append({
            "asin": asin,
            "client_id": client_id,
            "review_id": rid,
            "rating": r.get("rating", 0),
            "review_date": r.get("review_date", "2000-01-01")[:10], # Keep only YYYY-MM-DD
            "title": r.get("title", ""),
            "review_text": r.get("review_text", ""),
            "sentiment": str(r.get("sentiment", "neutral")).lower(),
            "scraped_at": now
        })
        
    if review_payloads:
        try:
            res = supabase.table("product_listing_reviews").upsert(review_payloads, on_conflict="review_id").execute()
            logging.info(f"    [SUPABASE] Upserted {len(review_payloads)} reviews successfully!")
        except Exception as e:
            logging.error(f"    [SUPABASE] Failed to upsert reviews: {e}")
            return False
            
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 3:
        run_reviews_scraper(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python3 reviews_scraper.py <ASIN> <CLIENT_ID> <MARKETPLACE>")
