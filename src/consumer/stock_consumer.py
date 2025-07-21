#!/usr/bin/env python3
"""
Stock Data Kafka Consumer
Consumes stock data from Kafka topics and writes partitioned files to S3.
"""

import os
import json
import time
import logging
import boto3
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from dotenv import load_dotenv
import pyarrow as pa
import pyarrow.parquet as pq

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/stock-pipeline/consumer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StockDataConsumer:
    """Kafka consumer for stock market data"""
    
    def __init__(self):
        self.kafka_broker = os.getenv('KAFKA_BROKER', 'localhost:9092')
        self.s3_bucket = os.getenv('S3_BUCKET')
        if not self.s3_bucket:
            raise ValueError("S3_BUCKET environment variable is required")
        
        # Initialize S3 client
        self.s3_client = boto3.client('s3')
        
        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            'stock-data',
            'stock-alerts',
            bootstrap_servers=[self.kafka_broker],
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            key_deserializer=lambda x: x.decode('utf-8') if x else None,
            group_id='stock-data-consumer-group',
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            auto_commit_interval_ms=1000
        )
        
        # Data buffers for batching
        self.stock_data_buffer = []
        self.alert_data_buffer = []
        self.batch_size = 100
        self.flush_interval = 60  # seconds
        
        # File rotation tracking
        self.current_date = datetime.now().date()
        self.last_flush_time = time.time()
        
        logger.info(f"Initialized consumer for bucket: {self.s3_bucket}")
    
    def get_s3_key(self, data_type: str, date: datetime.date, symbol: str = None) -> str:
        """Generate S3 key for partitioned storage"""
        year = date.year
        month = date.month
        day = date.day
        
        if data_type == 'stock-data':
            return f"raw/stock-data/year={year}/month={month:02d}/day={day:02d}/stock_data_{date}_{symbol}.parquet"
        elif data_type == 'alerts':
            return f"raw/alerts/year={year}/month={month:02d}/day={day:02d}/alerts_{date}.parquet"
        else:
            raise ValueError(f"Unknown data type: {data_type}")
    
    def write_to_s3(self, data: List[Dict], s3_key: str, data_type: str) -> bool:
        """Write data to S3 as Parquet file"""
        try:
            if not data:
                return True
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            
            # Add metadata columns
            df['ingested_at'] = datetime.utcnow().isoformat()
            df['data_type'] = data_type
            
            # Convert to Parquet
            table = pa.Table.from_pandas(df)
            
            # Write to temporary file
            temp_file = f"/tmp/{os.path.basename(s3_key)}"
            pq.write_table(table, temp_file)
            
            # Upload to S3
            with open(temp_file, 'rb') as f:
                self.s3_client.upload_fileobj(f, self.s3_bucket, s3_key)
            
            # Clean up temp file
            os.remove(temp_file)
            
            logger.info(f"Successfully wrote {len(data)} records to s3://{self.s3_bucket}/{s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing to S3: {e}")
            return False
    
    def flush_buffers(self, force: bool = False):
        """Flush data buffers to S3"""
        current_time = time.time()
        should_flush = force or (
            (len(self.stock_data_buffer) >= self.batch_size or 
             len(self.alert_data_buffer) >= self.batch_size) or
            (current_time - self.last_flush_time) >= self.flush_interval
        )
        
        if not should_flush:
            return
        
        # Flush stock data
        if self.stock_data_buffer:
            # Group by symbol for partitioning
            symbols_data = {}
            for record in self.stock_data_buffer:
                symbol = record['symbol']
                if symbol not in symbols_data:
                    symbols_data[symbol] = []
                symbols_data[symbol].append(record)
            
            # Write each symbol's data
            for symbol, data in symbols_data.items():
                s3_key = self.get_s3_key('stock-data', self.current_date, symbol)
                success = self.write_to_s3(data, s3_key, 'stock-data')
                if success:
                    logger.info(f"Flushed {len(data)} stock records for {symbol}")
            
            self.stock_data_buffer.clear()
        
        # Flush alert data
        if self.alert_data_buffer:
            s3_key = self.get_s3_key('alerts', self.current_date)
            success = self.write_to_s3(self.alert_data_buffer, s3_key, 'alerts')
            if success:
                logger.info(f"Flushed {len(self.alert_data_buffer)} alert records")
            
            self.alert_data_buffer.clear()
        
        self.last_flush_time = current_time
    
    def process_message(self, message):
        """Process a single Kafka message"""
        try:
            topic = message.topic
            key = message.key
            value = message.value
            
            # Add Kafka metadata
            value['kafka_topic'] = topic
            value['kafka_partition'] = message.partition
            value['kafka_offset'] = message.offset
            value['kafka_timestamp'] = message.timestamp
            
            if topic == 'stock-data':
                self.stock_data_buffer.append(value)
                logger.debug(f"Added stock data for {key}: {value['close']}")
                
            elif topic == 'stock-alerts':
                self.alert_data_buffer.append(value)
                logger.info(f"Alert for {key}: {value['alert_type']} at {value['current_price']}")
            
            # Check if we need to flush buffers
            self.flush_buffers()
            
            # Check if we need to rotate files (new day)
            current_date = datetime.now().date()
            if current_date != self.current_date:
                logger.info(f"Date changed from {self.current_date} to {current_date}, flushing buffers")
                self.current_date = current_date
                self.flush_buffers(force=True)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def run(self):
        """Main consumer loop"""
        logger.info("Starting stock data consumer...")
        
        try:
            for message in self.consumer:
                self.process_message(message)
                
        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            # Final flush before shutdown
            self.flush_buffers(force=True)
            self.consumer.close()

def main():
    """Main entry point"""
    try:
        consumer = StockDataConsumer()
        consumer.run()
    except Exception as e:
        logger.error(f"Failed to start consumer: {e}")
        raise

if __name__ == "__main__":
    main() 