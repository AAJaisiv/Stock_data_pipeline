#!/bin/bash

# Update system
yum update -y
yum install -y java-11-amazon-corretto wget unzip

# Set environment variables
export JAVA_HOME=/usr/lib/jvm/java-11-amazon-corretto
export PATH=$PATH:$JAVA_HOME/bin

# Create kafka user
useradd -r -s /bin/false kafka

# Install Zookeeper
cd /opt
wget https://archive.apache.org/dist/zookeeper/zookeeper-3.8.3/apache-zookeeper-3.8.3-bin.tar.gz
tar -xzf apache-zookeeper-3.8.3-bin.tar.gz
ln -s apache-zookeeper-3.8.3-bin zookeeper
chown -R kafka:kafka zookeeper

# Configure Zookeeper
mkdir -p /var/lib/zookeeper
chown kafka:kafka /var/lib/zookeeper

cat > /opt/zookeeper/conf/zoo.cfg << EOF
tickTime=2000
dataDir=/var/lib/zookeeper
clientPort=2181
initLimit=5
syncLimit=2
EOF

# Install Kafka
cd /opt
wget https://archive.apache.org/dist/kafka/3.5.1/kafka_2.13-3.5.1.tgz
tar -xzf kafka_2.13-3.5.1.tgz
ln -s kafka_2.13-3.5.1 kafka
chown -R kafka:kafka kafka

# Create Kafka directories
mkdir -p /var/lib/kafka-logs
chown kafka:kafka /var/lib/kafka-logs

# Configure Kafka
cat > /opt/kafka/config/server.properties << EOF
broker.id=0
log.dirs=/var/lib/kafka-logs
zookeeper.connect=localhost:2181
listeners=PLAINTEXT://:9092
advertised.listeners=PLAINTEXT://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):9092
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
cat > /etc/systemd/system/zookeeper.service << EOF
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
cat > /etc/systemd/system/kafka.service << EOF
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
systemctl daemon-reload
systemctl enable zookeeper
systemctl start zookeeper
systemctl enable kafka
systemctl start kafka

# Wait for services to start
sleep 30

# Create Kafka topics
/opt/kafka/bin/kafka-topics.sh --create --topic stock-data --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
/opt/kafka/bin/kafka-topics.sh --create --topic stock-alerts --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Install Python and pip
yum install -y python3 python3-pip

# Create application directory
mkdir -p /opt/stock-pipeline
chown -R kafka:kafka /opt/stock-pipeline

# Store S3 bucket name for applications
echo "${s3_bucket}" > /opt/stock-pipeline/s3_bucket.txt

# Create log directory
mkdir -p /var/log/stock-pipeline
chown kafka:kafka /var/log/stock-pipeline

echo "Kafka and Zookeeper installation completed!" 