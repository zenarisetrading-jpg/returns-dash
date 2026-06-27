import os
import time
import psycopg2
import logging
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from transformations.reviews_scraper import run_reviews_scraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)-13s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def _db_url():
    return os.environ.get("DATABASE_URL")

def get_asins_to_scrape():
    """Fetch distinct ASINs and their corresponding clients from fact_returns."""
    query = """
        SELECT DISTINCT f.asin, f.saddl_id
        FROM returns.fact_returns f
        WHERE f.asin IS NOT NULL AND f.asin != ''
    """
    
    asins = []
    try:
        with psycopg2.connect(_db_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                for row in cur.fetchall():
                    asins.append({
                        "asin": row[0],
                        "client_id": row[1],
                        "marketplace": "SA" if "ksa" in str(row[1]).lower() or "sa" in str(row[1]).lower() else "AE"
                    })
    except Exception as e:
        logging.error(f"Failed to fetch ASINs from database: {e}")
        
    return asins

def main():
    logging.info("Starting Daily Reviews Scraper Orchestrator...")
    
    asins_to_scrape = get_asins_to_scrape()
    logging.info(f"Found {len(asins_to_scrape)} unique ASINs to scrape.")
    
    success_count = 0
    fail_count = 0
    
    for item in asins_to_scrape:
        asin = item["asin"]
        client_id = item["client_id"]
        marketplace = item["marketplace"]
        
        logging.info(f"-> Scraping reviews for ASIN: {asin} ({client_id} / {marketplace})")
        
        # Scrape and Upsert
        success = run_reviews_scraper(asin, client_id, marketplace)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
            
        # Sleep to avoid aggressive rate limiting from Firecrawl/Amazon
        logging.info("Sleeping for 15 seconds to respect rate limits...")
        time.sleep(15)
        
    logging.info(f"Reviews scraping finished. Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    main()
