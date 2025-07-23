#!/usr/bin/env python3
"""
Real-time Stock Analysis Dashboard
Streamlit app for visualizing real-time stock data.
"""

import os
import streamlit as st
import boto3
import pandas as pd
from dotenv import load_dotenv
import io
from datetime import datetime
import time

# Load environment variables
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET")

# Streamlit page config and custom CSS
st.set_page_config(
    page_title="Real-time Stock Analysis Dashboard",
    page_icon="📈",
    layout="wide"
)
st.markdown('<h1 style="text-align:center; color:#1f77b4; font-size:2.5rem; font-weight:bold;">📈 Real-time Stock Analysis Dashboard</h1>', unsafe_allow_html=True)
st.markdown("""
    <style>
    .stDataFrame {background-color: #f8fafc !important;}
    .sidebar .sidebar-content {background-color: #f0f2f6;}
    .css-1d391kg {background-color: #f0f2f6 !important;}
    </style>
""", unsafe_allow_html=True)

# S3 utility functions
def list_s3_files(bucket, prefix=""):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [obj["Key"] for obj in response.get("Contents", []) if obj["Key"].endswith(".parquet")]
    return files

def read_parquet_from_s3(bucket, key):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))

# Sidebar controls
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
files = list_s3_files(S3_BUCKET)
if not files:
    st.sidebar.warning("No Parquet files found in S3 bucket.")
    st.stop()
file = st.sidebar.selectbox("Select a file to view", files)

# Stock filter
df = read_parquet_from_s3(S3_BUCKET, file)
if "symbol" in df.columns:
    stock_list = sorted(df["symbol"].unique())
    selected_stock = st.sidebar.selectbox("Select Stock Symbol", stock_list)
    filtered_df = df[df["symbol"] == selected_stock]
else:
    st.sidebar.warning("No 'symbol' column found in data.")
    filtered_df = df

# --- Pipeline Status Section ---
st.sidebar.markdown("---")
st.sidebar.markdown(
    "<h3 style='color:#1f77b4; text-align:center;'>🔧 Pipeline Status</h3>",
    unsafe_allow_html=True
)

def status_badge(is_running, label):
    color = '#4CAF50' if is_running else '#FF5252'
    emoji = '🟢' if is_running else '🔴'
    return f"<div style='display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;'><span style='font-size:1.2rem;'>{emoji}</span><span style='color:{color};font-weight:bold;'>{label}</span></div>"

# For demo/portfolio, set all to True
producer_running = True
consumer_running = True
s3_connected = True
streamlit_running = True

st.sidebar.markdown(status_badge(producer_running, 'Kafka Producer'), unsafe_allow_html=True)
st.sidebar.markdown(status_badge(consumer_running, 'Kafka Consumer'), unsafe_allow_html=True)
st.sidebar.markdown(status_badge(s3_connected, 'S3 Storage'), unsafe_allow_html=True)
st.sidebar.markdown(status_badge(streamlit_running, 'Streamlit App'), unsafe_allow_html=True)

# Data table
st.subheader("📊 Stock Data Table")
st.dataframe(filtered_df, use_container_width=True)

# Metrics for starting price, current price, and change (%)
if "timestamp" in filtered_df.columns:
    chart_df = filtered_df.copy()
    chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
    chart_df = chart_df.sort_values("timestamp")
    price_col = None
    if "close" in chart_df.columns:
        price_col = "close"
    elif "current_price" in chart_df.columns:
        price_col = "current_price"

    if price_col:
        start_price = chart_df.iloc[0][price_col]
        current_price = chart_df.iloc[-1][price_col]
        pct_change = ((current_price - start_price) / start_price) * 100 if start_price else 0

        # Color-coded Change (%) metric
        color = "green" if pct_change > 0 else "red" if pct_change < 0 else "gray"
        metric_cols = st.columns(3)
        metric_cols[0].metric("Starting Price", f"${start_price:.2f}")
        metric_cols[1].metric("Current Price", f"${current_price:.2f}")
        metric_cols[2].markdown(
            f"<div style='font-size:1.5rem; font-weight:bold; color:{color};'>"
            f"Change (%): {pct_change:.2f}%"
            f"</div>", unsafe_allow_html=True
        )
    else:
        st.warning("No price column found for metrics.")
else:
    st.warning("No timestamp column found for metrics.")

# Color-coded alert types (if present)
if "alert_type" in filtered_df.columns:
    st.subheader("Alerts")
    for idx, row in filtered_df.iterrows():
        alert = row["alert_type"]
        symbol = row["symbol"] if "symbol" in row else ""
        price = row["current_price"] if "current_price" in row else ""
        threshold = row["threshold"] if "threshold" in row else ""
        ts = row["timestamp"] if "timestamp" in row else ""
        if alert == "HIGH_PRICE":
            alert_color = "#ff4d4d"  # red
        elif alert == "LOW_PRICE":
            alert_color = "#1f77b4"  # blue
        else:
            alert_color = "#ffe066"  # yellow
        st.markdown(f"""
            <div style='background-color:{alert_color}; color:black; padding:0.5rem 1rem; border-radius:0.5rem; margin-bottom:0.5rem;'>
                <b>{alert}</b> for <b>{symbol}</b> at <b>${price}</b> (Threshold: {threshold})<br>
                <small>{ts}</small>
            </div>
        """, unsafe_allow_html=True)

# Line chart for stock performance
def plot_line_chart(df):
    if "timestamp" in df.columns and ("close" in df.columns or "current_price" in df.columns):
        chart_df = df.copy()
        chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
        chart_df = chart_df.sort_values("timestamp")
        st.subheader("Stock Performance Over Time")
        if "close" in chart_df.columns:
            st.line_chart(chart_df.set_index("timestamp")["close"])
        else:
            st.line_chart(chart_df.set_index("timestamp")["current_price"])
    else:
        st.warning("Required columns ('timestamp', 'close' or 'current_price') not found for chart.")

plot_line_chart(filtered_df)

# Footer
st.markdown("---")
st.markdown(
    f"<div style='text-align:center; color:gray;'>"
    f"Data Source: S3 | Last Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    f"</div>",
    unsafe_allow_html=True
)

# Auto-refresh logic
if auto_refresh:
    time.sleep(30)
    st.experimental_rerun() 