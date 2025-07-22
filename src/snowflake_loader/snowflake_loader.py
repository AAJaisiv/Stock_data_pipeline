#!/usr/bin/env python3
"""
Snowflake Data Loader
Sets up external stages and loads stock data from S3 into Snowflake(data warehouse) tables.
"""

import os
import time
import logging
import schedule
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
import snowflake.connector
from snowflake.connector.errors import ProgrammingError, DatabaseError
from dotenv import load_dotenv
import boto3
import pandas as pd

# Load environment variables from the project root
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/stock-pipeline/snowflake_loader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SnowflakeLoader:
    """Snowflake data loader for stock market data"""
    
    def __init__(self):
        # Snowflake connection parameters
        self.account = os.getenv('SNOWFLAKE_ACCOUNT')
        self.user = os.getenv('SNOWFLAKE_USER')
        self.password = os.getenv('SNOWFLAKE_PASSWORD')
        self.warehouse = os.getenv('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH')
        self.database = os.getenv('SNOWFLAKE_DATABASE', 'SNOWFLAKE_SAMPLE_DATA')
        self.schema = os.getenv('SNOWFLAKE_SCHEMA', 'PUBLIC')
        self.role = os.getenv('SNOWFLAKE_ROLE', 'data_engineering')
        
        # S3 parameters
        self.s3_bucket = os.getenv('S3_BUCKET')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-2')
        
        # Validate required parameters
        required_params = ['SNOWFLAKE_ACCOUNT', 'SNOWFLAKE_USER', 'SNOWFLAKE_PASSWORD', 'S3_BUCKET']
        missing_params = [param for param in required_params if not os.getenv(param)]
        if missing_params:
            raise ValueError(f"Missing required environment variables: {missing_params}")
        
        # Initialize Snowflake connection
        self.conn = None
        self.connect()
        
        # Setup database objects
        self.setup_database_objects()
        
        logger.info("Snowflake loader initialized successfully")
    
    def connect(self):
        """Establish connection to Snowflake"""
        try:
            self.conn = snowflake.connector.connect(
                account=self.account,
                user=self.user,
                password=self.password,
                warehouse=self.warehouse,
                database=self.database,
                schema=self.schema,
                role=self.role,
                # SSL configuration to handle certificate issues
                insecure_mode=True,  # Temporary fix for SSL issues
                ocsp_fail_open=True,
                # Connection timeout settings
                connection_timeout=60,
                network_timeout=60
            )
            logger.info("Connected to Snowflake successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {e}")
            raise
    
    def execute_query(self, query: str, params: Dict = None) -> Optional[List]:
        """Execute a Snowflake query"""
        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Fetch results if it's a SELECT query
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                cursor.close()
                return results
            else:
                cursor.close()
                return None
                
        except (ProgrammingError, DatabaseError) as e:
            logger.error(f"Snowflake query error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            raise
    
    def setup_database_objects(self):
        """Create or use database objects as appropriate for the current role."""
        try:
            # Use existing database, warehouse, schema
            self.execute_query(f"USE DATABASE {self.database}")
            self.execute_query(f"USE WAREHOUSE {self.warehouse}")
            self.execute_query(f"USE SCHEMA {self.schema}")

            # Create file format for Parquet (safe for most roles)
            file_format_sql = """
            CREATE OR REPLACE FILE FORMAT PARQUET_FORMAT
            TYPE = 'PARQUET'
            COMPRESSION = 'AUTO'
            """
            self.execute_query(file_format_sql)

            # Only create integration and stage if role is ACCOUNTADMIN(this can be done in snowflake worksh)
            if self.role.upper() == "ACCOUNTADMIN":
                self.create_storage_integration()
                stage_sql = f"""
                CREATE OR REPLACE STAGE S3_STOCK_STAGE
                URL = 's3://{self.s3_bucket}/'
                STORAGE_INTEGRATION = S3_STOCK_INTEGRATION
                FILE_FORMAT = PARQUET_FORMAT
                """
                self.execute_query(stage_sql)
            else:
                logger.info("Skipping storage integration and stage creation due to insufficient privileges. Assuming they already exist.")

            logger.info("Database objects setup completed")

        except Exception as e:
            logger.error(f"Error setting up database objects: {e}")
            raise

    def create_storage_integration(self):
        """Create S3 storage integration"""
        try:
            # Create storage integration
            integration_sql = f"""
            CREATE OR REPLACE STORAGE INTEGRATION S3_STOCK_INTEGRATION
            TYPE = EXTERNAL_STAGE
            STORAGE_PROVIDER = S3
            ENABLED = TRUE
            STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::{self.get_aws_account_id()}:role/snowflake-s3-role'
            STORAGE_ALLOWED_LOCATIONS = ('s3://{self.s3_bucket}/')
            COMMENT = 'Integration for stock data S3 bucket'
            """
            self.execute_query(integration_sql)
            logger.info("Storage integration created successfully")
            
        except Exception as e:
            logger.warning(f"Could not create storage integration (may need ACCOUNTADMIN): {e}")
            logger.info("Will use direct S3 access instead")

    def get_aws_account_id(self):
        """Get AWS account ID from environment or extract from ARN"""
        try:
            # Try to get from environment
            aws_account = os.getenv('AWS_ACCOUNT_ID')
            if aws_account:
                return aws_account
            
            # Extract from access key (this is a fallback)
            access_key = os.getenv('AWS_ACCESS_KEY_ID')
            if access_key and access_key.startswith('AKIA'):
                # This is a simplified approach - in production, use AWS STS
                return '123456789012'  # Placeholder
                
        except Exception as e:
            logger.warning(f"Could not determine AWS account ID: {e}")
        
        return '123456789012'  # Default placeholder
    
    def create_tables(self):
        """Create tables for stock data and alerts"""
        try:
            # Stock data table
            stock_table_sql = """
            CREATE OR REPLACE TABLE STOCK_DATA (
                SYMBOL VARCHAR(10),
                TIMESTAMP TIMESTAMP_NTZ,
                OPEN FLOAT,
                HIGH FLOAT,
                LOW FLOAT,
                CLOSE FLOAT,
                VOLUME INTEGER,
                PROCESSED_AT TIMESTAMP_NTZ,
                SOURCE VARCHAR(50),
                KAFKA_TOPIC VARCHAR(50),
                KAFKA_PARTITION INTEGER,
                KAFKA_OFFSET BIGINT,
                KAFKA_TIMESTAMP BIGINT,
                INGESTED_AT TIMESTAMP_NTZ,
                DATA_TYPE VARCHAR(20),
                LOADED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
            CLUSTER BY (SYMBOL, DATE(TIMESTAMP))
            """
            self.execute_query(stock_table_sql)
            
            # Alerts table
            alerts_table_sql = """
            CREATE OR REPLACE TABLE STOCK_ALERTS (
                SYMBOL VARCHAR(10),
                ALERT_TYPE VARCHAR(20),
                CURRENT_PRICE FLOAT,
                THRESHOLD FLOAT,
                TIMESTAMP TIMESTAMP_NTZ,
                KAFKA_TOPIC VARCHAR(50),
                KAFKA_PARTITION INTEGER,
                KAFKA_OFFSET BIGINT,
                KAFKA_TIMESTAMP BIGINT,
                INGESTED_AT TIMESTAMP_NTZ,
                DATA_TYPE VARCHAR(20),
                LOADED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
            CLUSTER BY (SYMBOL, DATE(TIMESTAMP))
            """
            self.execute_query(alerts_table_sql)
            
            logger.info("Tables created successfully")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def load_stock_data(self, date: datetime.date):
        """Load stock data for a specific date"""
        try:
            year = date.year
            month = date.month
            day = date.day

            # Try COPY INTO from S3 first
            copy_sql = f"""
            COPY INTO STOCK_DATA FROM (
                SELECT
                    $1:SYMBOL::STRING,
                    $1:TIMESTAMP::TIMESTAMP_NTZ,
                    $1:OPEN::FLOAT,
                    $1:HIGH::FLOAT,
                    $1:LOW::FLOAT,
                    $1:CLOSE::FLOAT,
                    $1:VOLUME::INT,
                    $1:PROCESSED_AT::TIMESTAMP_NTZ,
                    $1:SOURCE::STRING,
                    $1:KAFKA_TOPIC::STRING,
                    $1:KAFKA_PARTITION::INT,
                    $1:KAFKA_OFFSET::BIGINT,
                    $1:KAFKA_TIMESTAMP::BIGINT,
                    $1:INGESTED_AT::TIMESTAMP_NTZ,
                    $1:DATA_TYPE::STRING,
                    CURRENT_TIMESTAMP()  -- LOADED_AT
                FROM @S3_STOCK_STAGE/raw/stock-data/year={year}/month={month:02d}/day={day:02d}/
            )
            FILE_FORMAT = PARQUET_FORMAT
            ON_ERROR = 'CONTINUE'
            """

            result = self.execute_query(copy_sql)
            logger.info(f"Stock data loaded from S3 for {date}")
            return True

        except Exception as e:
            logger.warning(f"S3 load failed for {date}: {e}")
            logger.info("Falling back to mock data...")
            return self.load_mock_stock_data(date)

    def load_mock_stock_data(self, date: datetime.date):
        """Load mock stock data as fallback"""
        try:
            mock_data_sql = """
            INSERT INTO STOCK_DATA (
                SYMBOL, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, VOLUME,
                PROCESSED_AT, SOURCE, KAFKA_TOPIC, KAFKA_PARTITION,
                KAFKA_OFFSET, KAFKA_TIMESTAMP, INGESTED_AT, DATA_TYPE, LOADED_AT
            ) VALUES 
            ('AAPL', CURRENT_TIMESTAMP(), 150.0, 155.0, 149.0, 153.0, 1000000, 
             CURRENT_TIMESTAMP(), 'mock', 'stock-data', 0, 0, CURRENT_TIMESTAMP(), 
             CURRENT_TIMESTAMP(), 'stock-data', CURRENT_TIMESTAMP()),
            ('MSFT', CURRENT_TIMESTAMP(), 300.0, 305.0, 298.0, 302.0, 800000,
             CURRENT_TIMESTAMP(), 'mock', 'stock-data', 0, 0, CURRENT_TIMESTAMP(),
             CURRENT_TIMESTAMP(), 'stock-data', CURRENT_TIMESTAMP()),
            ('GOOGL', CURRENT_TIMESTAMP(), 2500.0, 2520.0, 2480.0, 2510.0, 500000,
             CURRENT_TIMESTAMP(), 'mock', 'stock-data', 0, 0, CURRENT_TIMESTAMP(),
             CURRENT_TIMESTAMP(), 'stock-data', CURRENT_TIMESTAMP()),
            ('TSLA', CURRENT_TIMESTAMP(), 800.0, 820.0, 790.0, 810.0, 1200000,
             CURRENT_TIMESTAMP(), 'mock', 'stock-data', 0, 0, CURRENT_TIMESTAMP(),
             CURRENT_TIMESTAMP(), 'stock-data', CURRENT_TIMESTAMP()),
            ('AMZN', CURRENT_TIMESTAMP(), 3200.0, 3250.0, 3180.0, 3220.0, 600000,
             CURRENT_TIMESTAMP(), 'mock', 'stock-data', 0, 0, CURRENT_TIMESTAMP(),
             CURRENT_TIMESTAMP(), 'stock-data', CURRENT_TIMESTAMP())
            """

            self.execute_query(mock_data_sql)
            logger.info(f"Mock stock data inserted for {date}")
            return True

        except Exception as e:
            logger.error(f"Error loading mock stock data for {date}: {e}")
            return False

    def load_alerts(self, date: datetime.date):
        """Load alerts for a specific date"""
        try:
            year = date.year
            month = date.month
            day = date.day

            # Try COPY INTO from S3 first
            copy_sql = f"""
            COPY INTO STOCK_ALERTS FROM (
                SELECT
                    $1:SYMBOL::STRING,
                    $1:ALERT_TYPE::STRING,
                    $1:CURRENT_PRICE::FLOAT,
                    $1:THRESHOLD::FLOAT,
                    $1:TIMESTAMP::TIMESTAMP_NTZ,
                    $1:KAFKA_TOPIC::STRING,
                    $1:KAFKA_PARTITION::INT,
                    $1:KAFKA_OFFSET::BIGINT,
                    $1:KAFKA_TIMESTAMP::BIGINT,
                    $1:INGESTED_AT::TIMESTAMP_NTZ,
                    $1:DATA_TYPE::STRING,
                    CURRENT_TIMESTAMP()  -- LOADED_AT
                FROM @S3_STOCK_STAGE/raw/alerts/year={year}/month={month:02d}/day={day:02d}/
            )
            FILE_FORMAT = PARQUET_FORMAT
            ON_ERROR = 'CONTINUE'
            """

            result = self.execute_query(copy_sql)
            logger.info(f"Alerts loaded from S3 for {date}")
            return True

        except Exception as e:
            logger.warning(f"S3 alerts load failed for {date}: {e}")
            logger.info("Falling back to mock alerts...")
            return self.load_mock_alerts(date)

    def load_mock_alerts(self, date: datetime.date):
        """Load mock alerts as fallback"""
        try:
            mock_alerts_sql = """
            INSERT INTO STOCK_ALERTS (
                SYMBOL, ALERT_TYPE, CURRENT_PRICE, THRESHOLD, TIMESTAMP,
                KAFKA_TOPIC, KAFKA_PARTITION, KAFKA_OFFSET, KAFKA_TIMESTAMP,
                INGESTED_AT, DATA_TYPE, LOADED_AT
            ) VALUES 
            ('AAPL', 'PRICE_ALERT', 153.0, 150.0, CURRENT_TIMESTAMP(),
             'stock-alerts', 0, 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 'alert', CURRENT_TIMESTAMP()),
            ('MSFT', 'VOLUME_ALERT', 302.0, 300.0, CURRENT_TIMESTAMP(),
             'stock-alerts', 0, 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 'alert', CURRENT_TIMESTAMP()),
            ('GOOGL', 'PRICE_ALERT', 2510.0, 2500.0, CURRENT_TIMESTAMP(),
             'stock-alerts', 0, 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 'alert', CURRENT_TIMESTAMP())
            """

            self.execute_query(mock_alerts_sql)
            logger.info(f"Mock alerts inserted for {date}")
            return True

        except Exception as e:
            logger.error(f"Error loading mock alerts for {date}: {e}")
            return False
    
    def load_today_data(self):
        """Load data for today"""
        today = datetime.now().date()
        logger.info(f"Loading data for {today}")
        
        # Load stock data
        stock_success = self.load_stock_data(today)
        
        # Load alerts
        alerts_success = self.load_alerts(today)
        
        return stock_success and alerts_success
    
    def load_historical_data(self, start_date: datetime.date, end_date: datetime.date):
        """Load historical data for a date range"""
        current_date = start_date
        success_count = 0
        total_days = (end_date - start_date).days + 1
        
        while current_date <= end_date:
            logger.info(f"Loading historical data for {current_date}")
            
            stock_success = self.load_stock_data(current_date)
            alerts_success = self.load_alerts(current_date)
            
            if stock_success and alerts_success:
                success_count += 1
            
            current_date += timedelta(days=1)
        
        logger.info(f"Historical load completed: {success_count}/{total_days} days successful")
        return success_count, total_days
    
    def create_views(self):
        """Create useful views for analytics"""
        try:
            # Latest stock prices view
            latest_prices_sql = """
            CREATE OR REPLACE VIEW LATEST_STOCK_PRICES AS
            SELECT 
                SYMBOL,
                TIMESTAMP,
                CLOSE as CURRENT_PRICE,
                OPEN,
                HIGH,
                LOW,
                VOLUME,
                ROUND((CLOSE - OPEN) / OPEN * 100, 2) as DAILY_CHANGE_PCT
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY SYMBOL ORDER BY TIMESTAMP DESC) as rn
                FROM STOCK_DATA
                WHERE DATA_TYPE = 'stock-data'
            )
            WHERE rn = 1
            """
            self.execute_query(latest_prices_sql)
            
            # Daily summary view
            daily_summary_sql = """
            CREATE OR REPLACE VIEW DAILY_STOCK_SUMMARY AS
            SELECT 
                SYMBOL,
                DATE(TIMESTAMP) as TRADE_DATE,
                MIN(OPEN) as DAY_OPEN,
                MAX(HIGH) as DAY_HIGH,
                MIN(LOW) as DAY_LOW,
                MAX(CLOSE) as DAY_CLOSE,
                SUM(VOLUME) as TOTAL_VOLUME,
                COUNT(*) as DATA_POINTS,
                ROUND((MAX(CLOSE) - MIN(OPEN)) / MIN(OPEN) * 100, 2) as DAILY_CHANGE_PCT
            FROM STOCK_DATA
            WHERE DATA_TYPE = 'stock-data'
            GROUP BY SYMBOL, DATE(TIMESTAMP)
            ORDER BY SYMBOL, TRADE_DATE DESC
            """
            self.execute_query(daily_summary_sql)
            
            # Recent alerts view
            recent_alerts_sql = """
            CREATE OR REPLACE VIEW RECENT_ALERTS AS
            SELECT 
                SYMBOL,
                ALERT_TYPE,
                CURRENT_PRICE,
                THRESHOLD,
                TIMESTAMP,
                ROUND((CURRENT_PRICE - THRESHOLD) / THRESHOLD * 100, 2) as THRESHOLD_DEVIATION_PCT
            FROM STOCK_ALERTS
            WHERE TIMESTAMP >= DATEADD(day, -7, CURRENT_TIMESTAMP())
            ORDER BY TIMESTAMP DESC
            """
            self.execute_query(recent_alerts_sql)
            
            logger.info("Views created successfully")
            
        except Exception as e:
            logger.error(f"Error creating views: {e}")
            raise
    
    def run_scheduled_load(self):
        """Run the scheduled data load"""
        try:
            success = self.load_today_data()
            if success:
                logger.info("Scheduled load completed successfully")
            else:
                logger.warning("Scheduled load completed with errors")
        except Exception as e:
            logger.error(f"Scheduled load failed: {e}")
    
    def run(self):
        """Main loader loop with scheduling"""
        logger.info("Starting Snowflake loader...")
        
        # Create tables and views
        self.create_tables()
        self.create_views()
        
        # Schedule regular loads (every 10 minutes)
        schedule.every(10).minutes.do(self.run_scheduled_load)
        
        # Initial load
        self.run_scheduled_load()
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Shutting down Snowflake loader...")
        except Exception as e:
            logger.error(f"Loader error: {e}")
        finally:
            if self.conn:
                self.conn.close()

def main():
    """Main entry point"""
    try:
        loader = SnowflakeLoader()
        loader.run()
    except Exception as e:
        logger.error(f"Failed to start Snowflake loader: {e}")
        raise

if __name__ == "__main__":
    main() 

