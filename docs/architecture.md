# Stock Data Pipeline Architecture

## Overview

This document provides a comprehensive guide to the real-time stock data pipeline architecture, including setup instructions, troubleshooting, and optimization strategies.

## Architecture Components

### 1. Data Ingestion Layer
- **Alpha Vantage API**: Free stock market data API
- **Kafka Producer**: Python application that fetches data every 5 seconds
- **Rate Limiting**: Handles API limits (5 calls/minute for free tier)

### 2. Message Queue Layer
- **Apache Kafka**: Distributed streaming platform
- **Zookeeper**: Coordination service for Kafka
- **Topics**: `stock-data` and `stock-alerts`

### 3. Data Storage Layer
- **AWS S3**: Raw data storage with partitioning
- **Parquet Format**: Columnar storage for efficient querying
- **Lifecycle Policies**: Automatic cost optimization

### 4. Data Warehouse Layer
- **Snowflake**: Cloud data warehouse
- **External Stages**: S3 integration
- **COPY INTO**: Automated data loading
- **Views**: Pre-aggregated data for analytics

### 5. Visualization Layer
- **Streamlit**: Real-time dashboard
- **Plotly**: Interactive charts
- **Caching**: Optimized query performance

## Infrastructure Setup

### Prerequisites

1. **AWS Account**: For EC2, S3, and IAM
2. **Snowflake Account**: For data warehouse
3. **Alpha Vantage API Key**: Free tier available
4. **Terraform**: For infrastructure provisioning

### Step 1: Infrastructure Provisioning

```bash
# Navigate to infrastructure directory
cd infra

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the infrastructure
terraform apply
```

**Important Notes:**
- Update `variables.tf` with your preferred region and instance type
- Ensure you have an AWS key pair for SSH access
- The S3 bucket name will be auto-generated with a random suffix

### Step 2: Kafka Setup

```bash
# SSH to the EC2 instance
ssh -i your-key.pem ec2-user@<EC2_PUBLIC_IP>

# Run the Kafka setup script
chmod +x scripts/setup_kafka.sh
./scripts/setup_kafka.sh
```

### Step 3: Environment Configuration

```bash
# Copy the example environment file
cp env.example .env

# Edit the environment file with your credentials
nano .env
```

**Required Environment Variables:**
- `ALPHA_VANTAGE_API_KEY`: Your Alpha Vantage API key
- `S3_BUCKET`: The S3 bucket name from Terraform output
- `SNOWFLAKE_ACCOUNT`: Your Snowflake account identifier
- `SNOWFLAKE_USER`: Snowflake username
- `SNOWFLAKE_PASSWORD`: Snowflake password

### Step 4: Snowflake Setup

1. **Create Storage Integration** (one-time setup):
```sql
-- Run in Snowflake console
CREATE STORAGE INTEGRATION S3_INTEGRATION
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = S3
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::YOUR_ACCOUNT:role/stock-pipeline-ec2-role'
  STORAGE_ALLOWED_LOCATIONS = ('s3://your-bucket-name/');
```

2. **Grant Permissions**:
```sql
GRANT USAGE ON INTEGRATION S3_INTEGRATION TO ROLE ACCOUNTADMIN;
```

### Step 5: Pipeline Deployment

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Deploy the pipeline
./scripts/deploy.sh
```

## Data Flow

### 1. Data Ingestion (5-second intervals)
```
Alpha Vantage API → Kafka Producer → stock-data topic
```

### 2. Data Processing
```
Kafka Consumer → S3 (Parquet files) → Snowflake (COPY INTO)
```

### 3. Data Visualization
```
Snowflake Views → Streamlit Dashboard → Real-time Charts
```

## Monitoring and Troubleshooting

### Log Files
- Producer: `/var/log/stock-pipeline/producer.log`
- Consumer: `/var/log/stock-pipeline/consumer.log`
- Snowflake Loader: `/var/log/stock-pipeline/snowflake_loader.log`
- Streamlit: `/var/log/stock-pipeline/streamlit.log`

### Common Issues and Solutions

#### 1. API Rate Limiting
**Symptoms**: "API Rate limit" messages in producer logs
**Solution**: 
- Upgrade to Alpha Vantage paid tier
- Increase `min_interval` in producer code
- Reduce number of stock symbols

#### 2. Kafka Connection Issues
**Symptoms**: "Connection refused" errors
**Solution**:
```bash
# Check Kafka status
sudo systemctl status kafka

# Restart Kafka if needed
sudo systemctl restart kafka

# Check topics
/opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092
```

#### 3. S3 Upload Failures
**Symptoms**: "Access Denied" errors in consumer logs
**Solution**:
- Verify IAM role permissions
- Check S3 bucket name in environment
- Ensure AWS credentials are configured

#### 4. Snowflake Connection Issues
**Symptoms**: "Authentication failed" errors
**Solution**:
- Verify Snowflake credentials in `.env`
- Check account identifier format
- Ensure user has proper permissions

#### 5. Streamlit Performance Issues
**Symptoms**: Slow dashboard loading
**Solution**:
- Increase cache TTL in `app.py`
- Add query limits to Snowflake queries
- Use warehouse auto-suspend

### Performance Optimization

#### 1. Cost Optimization
- **S3**: Enable Intelligent Tiering
- **Snowflake**: Use X-SMALL warehouse with auto-suspend
- **Streamlit**: Implement query caching

#### 2. Latency Optimization
- **Kafka**: Increase batch size in consumer
- **S3**: Use multipart uploads for large files
- **Snowflake**: Optimize COPY INTO frequency

#### 3. Scalability
- **Kafka**: Add more partitions for higher throughput
- **S3**: Implement data lifecycle policies
- **Snowflake**: Scale warehouse size as needed

## Security Considerations

### 1. Network Security
- VPC isolation for Kafka cluster
- Security groups with minimal required ports
- SSH key-based authentication

### 2. Data Security
- IAM roles with least privilege access
- Snowflake user with limited permissions
- API keys stored in environment variables

### 3. Monitoring
- CloudWatch logs for EC2
- Snowflake query history
- S3 access logs

## Maintenance

### Daily Tasks
- Monitor log files for errors
- Check pipeline component status
- Verify data freshness in dashboard

### Weekly Tasks
- Review Snowflake warehouse usage
- Check S3 storage costs
- Update stock symbols if needed

### Monthly Tasks
- Review and rotate API keys
- Update dependencies
- Performance analysis and optimization

## Backup and Recovery

### Data Backup
- S3 versioning enabled
- Snowflake Time Travel (7 days)
- Kafka log retention (7 days)

### Disaster Recovery
- Terraform state backup
- Environment configuration backup
- Documentation of manual setup steps

## Scaling Considerations

### Horizontal Scaling
- Multiple Kafka brokers
- Multiple consumer instances
- Load-balanced Streamlit instances

### Vertical Scaling
- Larger EC2 instance types
- Larger Snowflake warehouses
- Increased S3 storage classes

## Cost Estimation

### Monthly Costs (Estimated)
- **EC2 t3.medium**: ~$30/month
- **S3 Storage**: ~$5-10/month
- **Snowflake X-SMALL**: ~$25/month
- **Data Transfer**: ~$5/month
- **Total**: ~$65-70/month

### Cost Optimization Tips
- Use Spot Instances for non-critical workloads
- Implement S3 lifecycle policies
- Optimize Snowflake warehouse usage
- Monitor and adjust resources based on usage

## Support and Resources

### Documentation
- [Alpha Vantage API Documentation](https://www.alphavantage.co/documentation/)
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Snowflake Documentation](https://docs.snowflake.com/)
- [Streamlit Documentation](https://docs.streamlit.io/)

### Community Support
- GitHub Issues for code problems
- Stack Overflow for general questions
- AWS Support for infrastructure issues
- Snowflake Support for data warehouse issues 