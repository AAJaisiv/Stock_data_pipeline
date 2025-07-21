#!/bin/bash

# Stock Data Pipeline - Deployment Script
# This script deploys all components of the stock data pipeline

set -e

echo "🚀 Starting Stock Data Pipeline deployment..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "❌ Please don't run this script as root"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please create one with your configuration."
    echo "Example .env file:"
    cat << EOF
# Alpha Vantage API
ALPHA_VANTAGE_API_KEY=your_api_key_here

# Kafka Configuration
KAFKA_BROKER=localhost:9092
STOCK_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,TSLA

# AWS Configuration
AWS_REGION=us-east-1
S3_BUCKET=your-s3-bucket-name

# Snowflake Configuration
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=STOCK_PIPELINE
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_ROLE=ACCOUNTADMIN
EOF
    exit 1
fi

# Load environment variables
source .env

# Function to check if a service is running
check_service() {
    local service_name=$1
    local port=$2
    
    if netstat -tuln | grep -q ":$port "; then
        echo "✅ $service_name is running on port $port"
        return 0
    else
        echo "❌ $service_name is not running on port $port"
        return 1
    fi
}

# Function to install Python dependencies
install_dependencies() {
    local component=$1
    echo "📦 Installing dependencies for $component..."
    cd "src/$component"
    pip3 install -r requirements.txt
    cd ../..
}

# Check if Kafka is running
echo "🔍 Checking Kafka status..."
if ! check_service "Kafka" 9092; then
    echo "❌ Kafka is not running. Please start Kafka first:"
    echo "   sudo systemctl start kafka"
    exit 1
fi

if ! check_service "Zookeeper" 2181; then
    echo "❌ Zookeeper is not running. Please start Zookeeper first:"
    echo "   sudo systemctl start zookeeper"
    exit 1
fi

# Install dependencies for all components
echo "📦 Installing Python dependencies..."
install_dependencies "producer"
install_dependencies "consumer"
install_dependencies "snowflake_loader"
install_dependencies "streamlit_app"

# Create log directory if it doesn't exist
sudo mkdir -p /var/log/stock-pipeline
sudo chown $USER:$USER /var/log/stock-pipeline

# Function to start a component
start_component() {
    local component=$1
    local script=$2
    local log_file=$3
    
    echo "🚀 Starting $component..."
    cd "src/$component"
    nohup python3 $script > "/var/log/stock-pipeline/$log_file" 2>&1 &
    echo $! > "/tmp/stock-pipeline-$component.pid"
    cd ../..
    echo "✅ $component started with PID $(cat /tmp/stock-pipeline-$component.pid)"
}

# Start components
echo "🚀 Starting pipeline components..."

# Start producer
start_component "producer" "stock_producer.py" "producer.log"

# Wait a moment for producer to initialize
sleep 5

# Start consumer
start_component "consumer" "stock_consumer.py" "consumer.log"

# Wait a moment for consumer to initialize
sleep 5

# Start Snowflake loader
start_component "snowflake_loader" "snowflake_loader.py" "snowflake_loader.log"

# Function to check if a component is running
check_component() {
    local component=$1
    local pid_file="/tmp/stock-pipeline-$component.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo "✅ $component is running (PID: $pid)"
            return 0
        else
            echo "❌ $component is not running (PID file exists but process not found)"
            return 1
        fi
    else
        echo "❌ $component is not running (no PID file)"
        return 1
    fi
}

# Check all components
echo "🔍 Checking component status..."
sleep 10

check_component "producer"
check_component "consumer"
check_component "snowflake_loader"

# Start Streamlit dashboard
echo "🚀 Starting Streamlit dashboard..."
cd src/streamlit_app
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > "/var/log/stock-pipeline/streamlit.log" 2>&1 &
echo $! > "/tmp/stock-pipeline-streamlit.pid"
cd ../..

echo "✅ Streamlit dashboard started with PID $(cat /tmp/stock-pipeline-streamlit.pid)"

# Wait for Streamlit to start
sleep 10

# Check Streamlit
check_component "streamlit"

# Display status
echo ""
echo "🎉 Stock Data Pipeline deployment completed!"
echo ""
echo "📊 Component Status:"
echo "   Producer: $(check_component "producer" && echo "Running" || echo "Not Running")"
echo "   Consumer: $(check_component "consumer" && echo "Running" || echo "Not Running")"
echo "   Snowflake Loader: $(check_component "snowflake_loader" && echo "Running" || echo "Not Running")"
echo "   Streamlit Dashboard: $(check_component "streamlit" && echo "Running" || echo "Not Running")"
echo ""
echo "🌐 Access Points:"
echo "   Streamlit Dashboard: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8501"
echo "   Kafka Broker: localhost:9092"
echo "   Zookeeper: localhost:2181"
echo ""
echo "📝 Log Files:"
echo "   Producer: /var/log/stock-pipeline/producer.log"
echo "   Consumer: /var/log/stock-pipeline/consumer.log"
echo "   Snowflake Loader: /var/log/stock-pipeline/snowflake_loader.log"
echo "   Streamlit: /var/log/stock-pipeline/streamlit.log"
echo ""
echo "🛑 To stop the pipeline, run: ./scripts/stop.sh"
echo "📊 To monitor logs, run: tail -f /var/log/stock-pipeline/*.log" 