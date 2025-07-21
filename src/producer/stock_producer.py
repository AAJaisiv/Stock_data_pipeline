#!/usr/bin/env python3
"""
Stock Data Kafka Producer
Fetches real-time stock data from Alpha Vantage API and sends to Kafka topics.
"""

import os
import json
import time
import logging
import requests
import schedule
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
        logging.FileHandler('/var/log/stock-pipeline/producer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def fetch_from_finnhub(symbol, api_key):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("c") is not None:
                return {
                    'symbol': symbol,
                    'timestamp': int(time.time()),
                    'open': data.get('o'),
                    'high': data.get('h'),
                    'low': data.get('l'),
                    'close': data.get('c'),
                    'volume': data.get('v'),
                    'processed_at': datetime.utcnow().isoformat(),
                    'source': 'finnhub'
                }
    except Exception as e:
        logger.error(f"Finnhub error for {symbol}: {e}")
    return None

def fetch_from_twelvedata(symbol, api_key):
    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "price" in data:
                return {
                    'symbol': symbol,
                    'timestamp': int(time.time()),
                    'open': None,
                    'high': None,
                    'low': None,
                    'close': float(data["price"]),
                    'volume': None,
                    'processed_at': datetime.utcnow().isoformat(),
                    'source': 'twelvedata'
                }
    except Exception as e:
        logger.error(f"Twelve Data error for {symbol}: {e}")
    return None

class StockDataProducer:
    """Kafka producer for stock market data"""
    
    def __init__(self):
        self.finnhub_api_key = os.getenv('FINNHUB_API_KEY')
        self.twelvedata_api_key = os.getenv('TWELVE_DATA_API_KEY')
        if not (self.finnhub_api_key or self.twelvedata_api_key):
            raise ValueError("At least one of FINNHUB_API_KEY or TWELVE_DATA_API_KEY must be set in the environment.")
        
        self.kafka_broker = os.getenv('KAFKA_BROKER', 'localhost:9092')
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
        
        logger.info(f"Initialized producer for symbols: {self.stock_symbols}")
    
    def get_stock_data(self, symbol: str) -> Optional[Dict]:
        # Try Finnhub first
        data = fetch_from_finnhub(symbol, self.finnhub_api_key)
        if data:
            return data
        # If Finnhub fails, try Twelve Data
        data = fetch_from_twelvedata(symbol, self.twelvedata_api_key)
        if data:
            return data
        logger.warning(f"No data for {symbol} from either API.")
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
    
    def check_price_alerts(self, stock_data: Dict) -> List[Dict]:
        """Check for price alerts based on thresholds"""
        alerts = []
        symbol = stock_data['symbol']
        close_price = stock_data['close']
        
        # Define alert thresholds (in practice, these would come from a database)
        thresholds = {
            'AAPL': {'high': 200, 'low': 150},
            'MSFT': {'high': 400, 'low': 300},
            'GOOGL': {'high': 150, 'low': 120},
            'AMZN': {'high': 180, 'low': 140},
            'TSLA': {'high': 250, 'low': 200}
        }
        
        if symbol in thresholds:
            threshold = thresholds[symbol]
            
            if close_price > threshold['high']:
                alerts.append({
                    'symbol': symbol,
                    'alert_type': 'HIGH_PRICE',
                    'current_price': close_price,
                    'threshold': threshold['high'],
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            elif close_price < threshold['low']:
                alerts.append({
                    'symbol': symbol,
                    'alert_type': 'LOW_PRICE',
                    'current_price': close_price,
                    'threshold': threshold['low'],
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        return alerts
    
    def process_symbol(self, symbol: str):
        """Process a single stock symbol"""
        try:
            # Fetch stock data
            stock_data = self.get_stock_data(symbol)
            if not stock_data:
                return
            
            # Send to main stock-data topic
            success = self.send_to_kafka('stock-data', symbol, stock_data)
            if success:
                logger.info(f"Successfully sent data for {symbol}")
            
            # Check for price alerts
            alerts = self.check_price_alerts(stock_data)
            for alert in alerts:
                self.send_to_kafka('stock-alerts', symbol, alert)
                logger.info(f"Alert sent for {symbol}: {alert['alert_type']}")
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
    
    def run(self):
        """Main producer loop"""
        logger.info("Starting stock data producer...")
        
        try:
            while True:
                for symbol in self.stock_symbols:
                    self.process_symbol(symbol)
                    time.sleep(1)  # Small delay between symbols
                
                # Wait before next cycle (5 seconds as specified)
                logger.info("Completed cycle, waiting 5 seconds...")
                time.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("Shutting down producer...")
        except Exception as e:
            logger.error(f"Producer error: {e}")
        finally:
            self.producer.close()

def main():
    """Main entry point"""
    try:
        producer = StockDataProducer()
        producer.run()
    except Exception as e:
        logger.error(f"Failed to start producer: {e}")
        raise

if __name__ == "__main__":
    main() 