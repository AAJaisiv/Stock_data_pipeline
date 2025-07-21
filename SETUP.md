# Stock Data Pipeline - Setup Guide

This guide will walk you through setting up the complete real-time stock data pipeline from scratch.

## Prerequisites

Before starting, ensure you have:

1. **AWS Account** with appropriate permissions
2. **Snowflake Account** (free trial available)
3. **Alpha Vantage API Key** (free tier available)
4. **Terraform** installed locally
5. **SSH Key Pair** for AWS EC2 access

## Step 1: Get API Keys and Credentials

### Alpha Vantage API Key
1. Visit [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
2. Sign up for a free account
3. Copy your API key

### Snowflake Account
1. Sign up for [Snowflake free trial](https://www.snowflake.com/trial/)
2. Note your account identifier (e.g., `xy12345.us-east-1`)
3. Create a user and note credentials

### AWS Setup
1. Create an SSH key pair in AWS Console
2. Note the key name for Terraform configuration

## Step 2: Infrastructure Setup

### Update Terraform Configuration

Edit `infra/variables.tf`:
```hcl
variable "key_pair_name" {
  description = "Name of the AWS key pair for SSH access"
  type        = string
  default     = "your-key-pair-name"  # Update this
}
```

### Deploy Infrastructure

```bash
cd infra

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the infrastructure
terraform apply
```

**Note the outputs:**
- `kafka_public_ip`: EC2 instance IP
- `s3_bucket_name`: S3 bucket name

## Step 3: Kafka Setup

### SSH to EC2 Instance

```bash
ssh -i your-key.pem ec2-user@<KAFKA_PUBLIC_IP>
```

### Run Kafka Setup Script

```bash
# Clone the repository (if not already done)
git clone <your-repo-url>
cd Stock_data_pipeline

# Make script executable and run
chmod +x scripts/setup_kafka.sh
./scripts/setup_kafka.sh
```

**Expected output:**
```
✅ Zookeeper is running:
image.png
✅ Kafka is running
📋 Available Kafka topics: stock-data, stock-alerts
🎉 Kafka setup completed successfully!
```

## Step 4: Environment Configuration

### Create Environment File

```bash
# Copy example file
cp env.example .env

# Edit with your credentials
nano .env
```

**Required values:**
```bash
# Alpha Vantage API
ALPHA_VANTAGE_API_KEY=917QZOM4HTFG146D

# AWS Configuration
AWS_REGION=us-east-1
S3_BUCKET=stock-pipeline-raw-data-udm57xtt  # From Terraform output

# Snowflake ConfigurationWYHSRGP-QTB42213
SNOWFLAKE_ACCOUNT= WYHSRGP-QTB42213
SNOWFLAKE_USER= AAJaisiv1
SNOWFLAKE_PASSWORD= Abhinavjaisiv@0101
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=STOCK_DB
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_ROLE=SYSADMIN
```

## Step 5: Snowflake Setup

### Create Storage Integration

1. Log into Snowflake Console
2. Run the following SQL:

```sql
-- Create storage integration
CREATE STORAGE INTEGRATION S3_INTEGRATION
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = S3
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::872515279539:role/stock-pipeline-ec2-role'
  STORAGE_ALLOWED_LOCATIONS = ('s3://stock-pipeline-raw-data-udm57xtt/');

-- Grant permissions
GRANT USAGE ON INTEGRATION S3_INTEGRATION TO ROLE ACCOUNTADMIN;
```

**Replace:**
- `YOUR_AWS_ACCOUNT`: Your AWS account ID
- `YOUR_S3_BUCKET_NAME`: S3 bucket name from Terraform output

### Get AWS Account ID

```bash
# Run this on your local machine
aws sts get-caller-identity --query Account --output text
```

## Step 6: Deploy Pipeline

### Make Scripts Executable

```bash
chmod +x scripts/*.sh
```

### Deploy All Components

```bash
./scripts/deploy.sh
```

**Expected output:**
```
✅ Producer is running (PID: xxxx)
✅ Consumer is running (PID: xxxx)
✅ Snowflake Loader is running (PID: xxxx)
✅ Streamlit Dashboard is running (PID: xxxx)

🎉 Stock Data Pipeline deployment completed!

🌐 Access Points:
   Streamlit Dashboard: http://<EC2_IP>:8501
   Kafka Broker: localhost:9092
   Zookeeper: localhost:2181
```

## Step 7: Verify Setup

### Check Component Status

```bash
# Check if all components are running
ps aux | grep python

# Check logs
tail -f /var/log/stock-pipeline/*.log
```

### Access Dashboard

1. Open browser and navigate to: `http://<EC2_IP>:8501`
2. You should see the real-time stock dashboard
3. Verify that data is flowing by checking the metrics

### Test Data Flow

```bash
# Check Kafka topics
/opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092

# Check S3 for data files
aws s3 ls s3://your-bucket-name/raw/stock-data/ --recursive

# Check Snowflake tables
# Log into Snowflake console and run:
SELECT COUNT(*) FROM STOCK_DATA;
SELECT COUNT(*) FROM STOCK_ALERTS;
```

## Step 8: Monitoring and Maintenance

### Monitor Logs

```bash
# Real-time log monitoring
tail -f /var/log/stock-pipeline/producer.log
tail -f /var/log/stock-pipeline/consumer.log
tail -f /var/log/stock-pipeline/snowflake_loader.log
tail -f /var/log/stock-pipeline/streamlit.log
```

### Check Pipeline Status

```bash
# Check component PIDs
ls -la /tmp/stock-pipeline-*.pid

# Check service status
sudo systemctl status kafka
sudo systemctl status zookeeper
```

### Stop Pipeline

```bash
./scripts/stop.sh
```

### Restart Pipeline

```bash
./scripts/deploy.sh
```

## Troubleshooting

### Common Issues

#### 1. API Rate Limiting
**Symptoms:** "API Rate limit" in producer logs
**Solution:** Wait for rate limit to reset or upgrade API tier

#### 2. Kafka Connection Issues
**Symptoms:** "Connection refused" errors
**Solution:**
```bash
sudo systemctl restart kafka
sudo systemctl restart zookeeper
```

#### 3. S3 Upload Failures
**Symptoms:** "Access Denied" in consumer logs
**Solution:** Verify IAM role and S3 bucket permissions

#### 4. Snowflake Connection Issues
**Symptoms:** "Authentication failed"
**Solution:** Check credentials in `.env` file

#### 5. Streamlit Not Loading
**Symptoms:** Dashboard not accessible
**Solution:**
```bash
# Check if Streamlit is running
ps aux | grep streamlit

# Restart if needed
pkill -f streamlit
cd src/streamlit_app
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
```

### Performance Optimization

#### 1. Reduce Costs
- Use smaller EC2 instance if possible
- Enable S3 lifecycle policies
- Use Snowflake warehouse auto-suspend

#### 2. Improve Performance
- Increase Kafka batch sizes
- Optimize Snowflake query patterns
- Use Streamlit caching effectively

#### 3. Scale Up
- Add more Kafka partitions
- Use larger EC2 instances
- Scale Snowflake warehouse size

## Security Best Practices

### 1. Network Security
- Use VPC with private subnets
- Restrict security group rules
- Use SSH key-based authentication

### 2. Data Security
- Rotate API keys regularly
- Use IAM roles with minimal permissions
- Enable S3 bucket encryption

### 3. Access Control
- Limit Snowflake user permissions
- Use environment variables for secrets
- Monitor access logs

## Cost Optimization

### Monthly Cost Breakdown
- **EC2 t3.medium**: ~$30/month
- **S3 Storage**: ~$5-10/month
- **Snowflake X-SMALL**: ~$25/month
- **Data Transfer**: ~$5/month
- **Total**: ~$65-70/month

### Cost Reduction Tips
1. Use Spot Instances for non-critical workloads
2. Implement S3 lifecycle policies
3. Optimize Snowflake warehouse usage
4. Monitor and adjust resources based on usage

## Next Steps

### Enhancements
1. Add more stock symbols
2. Implement advanced analytics
3. Add alerting and notifications
4. Create additional dashboards

### Production Considerations
1. Set up monitoring and alerting
2. Implement backup and recovery
3. Add security scanning
4. Create CI/CD pipeline

### Scaling
1. Add multiple Kafka brokers
2. Implement load balancing
3. Use managed services (MSK, EMR)
4. Add data quality checks

## Support

### Documentation
- [Architecture Guide](docs/architecture.md)
- [Troubleshooting Guide](docs/architecture.md#monitoring-and-troubleshooting)
- [API Documentation](https://www.alphavantage.co/documentation/)

### Community
- GitHub Issues for code problems
- Stack Overflow for general questions
- AWS Support for infrastructure issues
- Snowflake Support for data warehouse issues

---

**Congratulations!** You now have a fully functional real-time stock data pipeline running in the cloud. The system will automatically collect, process, and visualize stock market data with minimal maintenance required. 