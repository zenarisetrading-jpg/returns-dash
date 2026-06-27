import os
import json
import time
import requests
import asyncio
from supabase import create_client, Client
from datetime import datetime, timezone
import logging
from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
    return f"https://www.amazon.{tld}/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?sortBy=recent"

def scrape_with_scrapergraph(asin: str, marketplace: str):
    """Tier 1: ScrapeGraphAI (Primary)"""
    sgai_key = os.environ.get("SGAI_API_KEY")
    if not sgai_key:
        logging.warning("No SGAI_API_KEY found, skipping ScrapeGraphAI.")
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
        response = requests.post("https://api.scrapegraphai.com/v1/smartscraper", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
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

async def _crawl4ai_fetch(url: str) -> str:
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown

def scrape_with_crawl4ai_anthropic(asin: str, marketplace: str):
    """Tier 2: Local Crawl4AI + Anthropic LLM Parsing (Fallback)"""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logging.warning("No ANTHROPIC_API_KEY found, skipping Crawl4AI + LLM fallback.")
        return None

    url = get_amazon_url(asin, marketplace)
    logging.info(f"    [CRAWL4AI] Attempting local crawl for {url}")
    
    try:
        # Run local chromium scraper asynchronously
        markdown_content = asyncio.run(_crawl4ai_fetch(url))
        
        if not markdown_content or len(markdown_content) < 100:
            logging.error("    [CRAWL4AI] Failed to extract meaningful markdown.")
            return None
            
        logging.info("    [CRAWL4AI] Successfully crawled page, sending to Anthropic for parsing...")
        
        client = Anthropic(api_key=anthropic_key)
        prompt = f"""
        Extract the Amazon customer reviews and overall rating metrics from the following markdown scraped from an Amazon Product Reviews page.
        
        Return ONLY a raw, valid JSON object that strictly adheres to this schema:
        {{
            "star_rating": 4.5,
            "total_reviews": 120,
            "one_star_pct": 5,
            "two_star_pct": 2,
            "three_star_pct": 8,
            "four_star_pct": 15,
            "five_star_pct": 70,
            "reviews": [
                {{
                    "review_id": "string (extract from URL/ID if available, else omit)",
                    "rating": 5,
                    "review_date": "YYYY-MM-DD",
                    "title": "string",
                    "review_text": "string",
                    "sentiment": "positive | neutral | negative"
                }}
            ]
        }}
        
        Markdown Content:
        {markdown_content[:20000]}  # Trim to avoid exceeding context
        """
        
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse the JSON response
        text = response.content[0].text
        # Clean potential markdown block formatting
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()
            
        return json.loads(text)
        
    except Exception as e:
        logging.error(f"    [CRAWL4AI/LLM] Exception occurred: {e}")
        return None

def scrape_with_firecrawl(asin: str, marketplace: str):
    """Tier 3: Firecrawl Extract API (Last Resort)"""
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
            "star_rating": {"type": "number"},
            "total_reviews": {"type": "number"},
            "one_star_pct": {"type": "number"},
            "two_star_pct": {"type": "number"},
            "three_star_pct": {"type": "number"},
            "four_star_pct": {"type": "number"},
            "five_star_pct": {"type": "number"},
            "reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "review_id": {"type": "string"},
                        "rating": {"type": "number"},
                        "review_date": {"type": "string"},
                        "title": {"type": "string"},
                        "review_text": {"type": "string"},
                        "sentiment": {"type": "string"}
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
            "prompt": "Extract the overall product listing health (star ratings, percentages) and the list of individual recent customer reviews."
        }
    }
    
    try:
        response = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and "extract" in data.get("data", {}):
            return data["data"]["extract"]
        else:
            logging.error(f"    [FIRECRAWL] Success but no extract data: {data}")
    except Exception as e:
        logging.error(f"    [FIRECRAWL] Exception occurred: {e}")
        
    return None

def run_reviews_scraper(asin: str, client_id: str, marketplace: str):
    """Main extraction logic running through the 3-Tier Fallback."""
    
    # 1. ScrapeGraphAI (Primary Cloud)
    data = scrape_with_scrapergraph(asin, marketplace)
    
    # 2. Crawl4AI + Anthropic (Local Fallback)
    if not data or not data.get("reviews"):
        logging.warning("    [!] ScrapeGraphAI failed. Falling back to Crawl4AI (Local).")
        data = scrape_with_crawl4ai_anthropic(asin, marketplace)
        
    # 3. Firecrawl (Final Cloud Fallback)
    if not data or not data.get("reviews"):
        logging.warning("    [!] Crawl4AI failed. Falling back to Firecrawl.")
        data = scrape_with_firecrawl(asin, marketplace)
        
    if not data or not data.get("reviews"):
        logging.error(f"    [X] All scraper tiers failed for ASIN {asin}")
        return False
        
    logging.info(f"    [SUCCESS] Scraped {len(data['reviews'])} reviews for {asin}")
    
    # Prepare Data for Upsert
    now = datetime.now(timezone.utc).isoformat()
    supabase = _db_client()
    
    # Upsert Health
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
            supabase.table("product_listing_health").upsert(health_payload, on_conflict="asin,client_id").execute()
        except Exception as e:
            logging.error(f"    [SUPABASE] Failed to upsert health: {e}")
            
    # Upsert Reviews
    review_payloads = []
    for r in data["reviews"]:
        rid = str(r.get("review_id", ""))
        if not rid or len(rid) < 5:
            import hashlib
            rid = hashlib.md5(f"{asin}{r.get('review_text')}".encode()).hexdigest()
            
        review_payloads.append({
            "asin": asin,
            "client_id": client_id,
            "review_id": rid,
            "rating": r.get("rating", 0),
            "review_date": r.get("review_date", "2000-01-01")[:10],
            "title": r.get("title", ""),
            "review_text": r.get("review_text", ""),
            "sentiment": str(r.get("sentiment", "neutral")).lower(),
            "scraped_at": now
        })
        
    if review_payloads:
        try:
            supabase.table("product_listing_reviews").upsert(review_payloads, on_conflict="review_id").execute()
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
