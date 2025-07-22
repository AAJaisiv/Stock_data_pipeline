#!/usr/bin/env python3
"""
Test Stock Data Producer (Local Testing)
Fetches real-time stock data from Alpha Vantage API for testing
Tested this on Sunday as market was closed.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv

# Loading environment variables
load_dotenv()

# Configure logging to console only for testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TestStockDataProducer:
    """Test version of Kafka producer for stock market data"""
    
    def __init__(self):
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        if not self.api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is required")
        
        # Test with just one symbol to avoid rate limits
        self.stock_symbols = ['AAPL']  # Just testing with Apple
        
        # Rate limiting (Alpha Vantage free tier: 5 calls/minute)
        self.last_api_call = {}
        self.min_interval = 12  # seconds between calls per symbol
        
        logger.info(f"Initialized test producer for symbols: {self.stock_symbols}")
        logger.info(f"API Key: {self.api_key[:8]}...")  #to Show first 8 chars
    
    def get_stock_data(self, symbol: str) -> Optional[Dict]:
        """Fetch stock data from Alpha Vantage API"""
        try:
            # Rate limiting check
            if symbol in self.last_api_call:
                time_since_last = time.time() - self.last_api_call[symbol]
                if time_since_last < self.min_interval:
                    sleep_time = self.min_interval - time_since_last
                    logger.info(f"Rate limiting: sleeping {sleep_time:.2f}s for {symbol}")
                    time.sleep(sleep_time)
            
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_INTRADAY',
                'symbol': symbol,
                'interval': '1min',
                'apikey': self.api_key,
                'outputsize': 'compact'
            }
            
            logger.info(f"Fetching data for {symbol}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            self.last_api_call[symbol] = time.time()
            
            # Checking for API errors
            if 'Error Message' in data:
                logger.error(f"API Error for {symbol}: {data['Error Message']}")
                return None
            
            if 'Note' in data:
                logger.warning(f"API Rate limit for {symbol}: {data['Note']}")
                return None
            
            # Extracting latest data point
            time_series = data.get('Time Series (1min)', {})
            if not time_series:
                logger.warning(f"No time series data for {symbol}")
                return None
            
            # Getting the most recent timestamp
            latest_timestamp = max(time_series.keys())
            latest_data = time_series[latest_timestamp]
            
            # Prepare stock data messages
            stock_message = {
                'symbol': symbol,
                'timestamp': latest_timestamp,
                'open': float(latest_data['1. open']),
                'high': float(latest_data['2. high']),
                'low': float(latest_data['3. low']),
                'close': float(latest_data['4. close']),
                'volume': int(latest_data['5. volume']),
                'processed_at': datetime.utcnow().isoformat(),
                'source': 'alpha_vantage'
            }
            
            logger.info(f"Successfully fetched data for {symbol}: ${stock_message['close']}")
            return stock_message
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {symbol}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Data parsing error for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {symbol}: {e}")
            return None
    
    def test_api_connection(self):
        """Test API connection and data fetching"""
        logger.info("🧪 Testing Alpha Vantage API connection...")
        
        for symbol in self.stock_symbols:
            logger.info(f"Testing symbol: {symbol}")
            stock_data = self.get_stock_data(symbol)
            
            if stock_data:
                logger.info("API Test Successful!")
                logger.info(f"Sample data: {json.dumps(stock_data, indent=2)}")
                return True
            else:
                logger.error("API Test Failed!")
                return False
    
    def run_test(self):
        """Run a simple test"""
        logger.info(" Starting test producer...")
        
        try:
            # Testing the API connection
            if self.test_api_connection():
                logger.info("All tests passed! Producer is ready for deployment.")
            else:
                logger.error("Tests failed. Check your API key and network connection.")
                
        except KeyboardInterrupt:
            logger.info("Shutting down test producer...")
        except Exception as e:
            logger.error(f"Test producer error: {e}")
            raise

def main():
    """Main entry point"""
    try:
        producer = TestStockDataProducer()
        producer.run_test()
    except Exception as e:
        logger.error(f"Failed to start test producer: {e}")
        raise

if __name__ == "__main__":
    main() 