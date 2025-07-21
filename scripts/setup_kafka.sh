#!/bin/bash

# Stock Data Pipeline - Kafka Setup Script
# This script sets up Kafka and Zookeeper on an EC2 instance

set -e

echo "🚀 Starting Kafka setup..."

# Update system packages
echo "📦 Updating system packages..."
sudo yum update -y

# Install Java
echo "☕ Installing Java..."
sudo yum install -y java-11-amazon-corretto

# Set Java environment variables
export JAVA_HOME=/usr/lib/jvm/java-11-amazon-corretto
export PATH=$PATH:$JAVA_HOME/bin

# Create kafka user
echo "👤 Creating kafka user..."
sudo useradd -r -s /bin/false kafka

# Install Zookeeper
echo "🐘 Installing Zookeeper..."
cd /opt
sudo wget https://archive.apache.org/dist/zookeeper/zookeeper-3.8.3/apache-zookeeper-3.8.3-bin.tar.gz
sudo tar -xzf apache-zookeeper-3.8.3-bin.tar.gz
sudo ln -s apache-zookeeper-3.8.3-bin zookeeper
sudo chown -R kafka:kafka zookeeper

# Configure Zookeeper
echo "⚙️ Configuring Zookeeper..."
sudo mkdir -p /var/lib/zookeeper
sudo chown kafka:kafka /var/lib/zookeeper

sudo tee /opt/zookeeper/conf/zoo.cfg > /dev/null << EOF
tickTime=2000
dataDir=/var/lib/zookeeper
clientPort=2181
initLimit=5
syncLimit=2
EOF

# Install Kafka
echo "📨 Installing Kafka..."
cd /opt
sudo wget https://archive.apache.org/dist/kafka/3.5.1/kafka_2.13-3.5.1.tgz
sudo tar -xzf kafka_2.13-3.5.1.tgz
sudo ln -s kafka_2.13-3.5.1 kafka
sudo chown -R kafka:kafka kafka

# Create Kafka directories
sudo mkdir -p /var/lib/kafka-logs
sudo chown kafka:kafka /var/lib/kafka-logs

# Get public IP for Kafka configuration
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

# Configure Kafka
echo "⚙️ Configuring Kafka..."
sudo tee /opt/kafka/config/server.properties > /dev/null << EOF
broker.id=0
log.dirs=/var/lib/kafka-logs
zookeeper.connect=localhost:2181
listeners=PLAINTEXT://:9092
advertised.listeners=PLAINTEXT://${PUBLIC_IP}:9092
num.network.threads=3
num.io.threads=8
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600
num.partitions=1
num.recovery.threads.per.data.dir=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000
EOF

# Create systemd service for Zookeeper
echo "🔧 Creating Zookeeper systemd service..."
sudo tee /etc/systemd/system/zookeeper.service > /dev/null << EOF
[Unit]
Description=Apache Zookeeper
After=network.target

[Service]
Type=forking
User=kafka
Group=kafka
Environment=JAVA_HOME=/usr/lib/jvm/java-11-amazon-corretto
ExecStart=/opt/zookeeper/bin/zkServer.sh start
ExecStop=/opt/zookeeper/bin/zkServer.sh stop
ExecReload=/opt/zookeeper/bin/zkServer.sh restart
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for Kafka
echo "🔧 Creating Kafka systemd service..."
sudo tee /etc/systemd/system/kafka.service > /dev/null << EOF
[Unit]
Description=Apache Kafka
After=zookeeper.service

[Service]
Type=simple
User=kafka
Group=kafka
Environment=JAVA_HOME=/usr/lib/jvm/java-11-amazon-corretto
ExecStart=/opt/kafka/bin/kafka-server-start.sh /opt/kafka/config/server.properties
ExecStop=/opt/kafka/bin/kafka-server-stop.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable zookeeper
sudo systemctl start zookeeper
sudo systemctl enable kafka
sudo systemctl start kafka

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 30

# Create Kafka topics
echo "📝 Creating Kafka topics..."
/opt/kafka/bin/kafka-topics.sh --create --topic stock-data --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
/opt/kafka/bin/kafka-topics.sh --create --topic stock-alerts --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Install Python and pip
echo "🐍 Installing Python..."
sudo yum install -y python3 python3-pip

# Create application directory
echo "📁 Creating application directory..."
sudo mkdir -p /opt/stock-pipeline
sudo chown -R kafka:kafka /opt/stock-pipeline

# Create log directory
sudo mkdir -p /var/log/stock-pipeline
sudo chown kafka:kafka /var/log/stock-pipeline

# Verify services are running
echo "✅ Verifying services..."
if sudo systemctl is-active --quiet zookeeper; then
    echo "✅ Zookeeper is running"
else
    echo "❌ Zookeeper failed to start"
    exit 1
fi

if sudo systemctl is-active --quiet kafka; then
    echo "✅ Kafka is running"
else
    echo "❌ Kafka failed to start"
    exit 1
fi

# List topics
echo "📋 Available Kafka topics:"
/opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092

echo "🎉 Kafka setup completed successfully!"
echo "📊 Kafka is running on port 9092"
echo "🐘 Zookeeper is running on port 2181"
echo "📝 Topics created: stock-data, stock-alerts" 