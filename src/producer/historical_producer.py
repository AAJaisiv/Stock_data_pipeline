#!/usr/bin/env python3
"""
Historical Stock Data Kafka Producer
created this to fetch data on non-market hours.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/stock-pipeline/historical_producer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HistoricalStockDataProducer:
    """Kafka producer for historical stock market data"""
    
    def __init__(self):
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        if not self.api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is required")
        
        self.kafka_broker = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        self.stock_symbols = os.getenv('STOCK_SYMBOLS', 'AAPL,MSFT,GOOGL,AMZN,TSLA').split(',')
        
        # Initialize Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=[self.kafka_broker],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            retries=3,
            acks='all'
        )
        
        # Rate limiting (Alpha Vantage free tier: 5 calls/minute)
        self.last_api_call = {}
        self.min_interval = 12  # seconds between calls per symbol
        
        logger.info(f"Initialized historical producer for symbols: {self.stock_symbols}")
    
    def get_historical_data(self, symbol: str, days_back: int = 30) -> Optional[List[Dict]]:
        """Fetch historical daily stock data from Alpha Vantage API"""
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
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'apikey': self.api_key,
                'outputsize': 'compact'  # Last 100 data points
            }
            
            logger.info(f"Fetching historical data for {symbol} (last {days_back} days)")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            self.last_api_call[symbol] = time.time()
            
            # Check for API errors
            if 'Error Message' in data:
                logger.error(f"API Error for {symbol}: {data['Error Message']}")
                return None
            
            if 'Note' in data:
                logger.warning(f"API Rate limit for {symbol}: {data['Note']}")
                return None
            
            # Extract daily time series data
            time_series = data.get('Time Series (Daily)', {})
            if not time_series:
                logger.warning(f"No daily time series data for {symbol}")
                return None
            
            # Convert to list and sort by date (newest first)
            daily_data = []
            for date, values in time_series.items():
                daily_data.append({
                    'date': date,
                    'open': float(values['1. open']),
                    'high': float(values['2. high']),
                    'low': float(values['3. low']),
                    'close': float(values['4. close']),
                    'volume': int(values['5. volume'])
                })
            
            # Sort by date (newest first) and limit to requested days
            daily_data.sort(key=lambda x: x['date'], reverse=True)
            daily_data = daily_data[:days_back]
            
            logger.info(f"Retrieved {len(daily_data)} days of data for {symbol}")
            return daily_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {symbol}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Data parsing error for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {symbol}: {e}")
            return None
    
    def send_to_kafka(self, topic: str, key: str, message: Dict) -> bool:
        """Send message to Kafka topic"""
        try:
            future = self.producer.send(topic, key=key, value=message)
            record_metadata = future.get(timeout=10)
            
            logger.info(
                f"Message sent to {topic} - "
                f"Partition: {record_metadata.partition}, "
                f"Offset: {record_metadata.offset}"
            )
            return True
            
        except KafkaError as e:
            logger.error(f"Kafka error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending to Kafka: {e}")
            return False
    
    def process_symbol(self, symbol: str, days_back: int = 30):
        """Process historical data for a single stock symbol"""
        try:
            # Fetch historical data
            historical_data = self.get_historical_data(symbol, days_back)
            if not historical_data:
                return
            
            # Send each day's data to Kafka
            for day_data in historical_data:
                # Prepare stock data message
                stock_message = {
                    'symbol': symbol,
                    'date': day_data['date'],
                    'open': day_data['open'],
                    'high': day_data['high'],
                    'low': day_data['low'],
                    'close': day_data['close'],
                    'volume': day_data['volume'],
                    'processed_at': datetime.utcnow().isoformat(),
                    'source': 'alpha_vantage_historical',
                    'data_type': 'daily'
                }
                
                # Send to Kafka
                success = self.send_to_kafka('stock-data', symbol, stock_message)
                if success:
                    logger.info(f"Sent historical data for {symbol} on {day_data['date']}: ${day_data['close']}")
                
                # Small delay between messages
                time.sleep(0.1)
            
            logger.info(f"Completed processing {len(historical_data)} days for {symbol}")
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
    
    def run(self, days_back: int = 30):
        """Main producer loop for historical data"""
        logger.info(f"Starting historical stock data producer (last {days_back} days)...")
        
        try:
            for symbol in self.stock_symbols:
                logger.info(f"Processing historical data for {symbol}")
                self.process_symbol(symbol, days_back)
                time.sleep(2)  # Delay between symbols
            
            logger.info("Historical data processing completed!")
            
        except KeyboardInterrupt:
            logger.info("Shutting down historical producer...")
        except Exception as e:
            logger.error(f"Historical producer error: {e}")
        finally:
            self.producer.close()

def main():
    """Main entry point"""
    try:
        producer = HistoricalStockDataProducer()
        # Pull last 7 days of data
        producer.run(days_back=7)
    except Exception as e:
        logger.error(f"Failed to start historical producer: {e}")
        raise

if __name__ == "__main__":
    main() 