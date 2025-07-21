#!/bin/bash

# Stock Data Pipeline - Stop Script
# This script stops all components of the stock data pipeline

echo "🛑 Stopping Stock Data Pipeline..."

# Function to stop a component
stop_component() {
    local component=$1
    local pid_file="/tmp/stock-pipeline-$component.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo "🛑 Stopping $component (PID: $pid)..."
            kill $pid
            sleep 2
            
            # Check if process is still running
            if ps -p $pid > /dev/null 2>&1; then
                echo "⚠️  $component didn't stop gracefully, force killing..."
                kill -9 $pid
            fi
            
            rm -f "$pid_file"
            echo "✅ $component stopped"
        else
            echo "ℹ️  $component is not running"
            rm -f "$pid_file"
        fi
    else
        echo "ℹ️  $component is not running (no PID file)"
    fi
}

# Stop all components
echo "🛑 Stopping pipeline components..."

stop_component "producer"
stop_component "consumer"
stop_component "snowflake_loader"
stop_component "streamlit"

echo ""
echo "🎉 All pipeline components stopped!"
echo ""
echo "📝 To restart the pipeline, run: ./scripts/deploy.sh"
echo "📊 To check logs, run: tail -f /var/log/stock-pipeline/*.log" 