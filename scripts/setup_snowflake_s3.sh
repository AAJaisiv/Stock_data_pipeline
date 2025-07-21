#!/bin/bash

# Setup Snowflake S3 Integration
# This script creates the necessary AWS IAM role and permissions for Snowflake to access S3

set -e

# Load environment variables
source ../.env

echo "🔧 Setting up Snowflake S3 Integration..."

# Validate required environment variables
if [ -z "$S3_BUCKET" ]; then
    echo "❌ Error: S3_BUCKET not set in .env file"
    exit 1
fi

if [ -z "$SNOWFLAKE_ACCOUNT" ]; then
    echo "❌ Error: SNOWFLAKE_ACCOUNT not set in .env file"
    exit 1
fi

# Get AWS account ID
echo "📋 Getting AWS account ID..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to get AWS account ID. Check AWS credentials."
    exit 1
fi
echo "✅ AWS Account ID: $AWS_ACCOUNT_ID"

# Convert Snowflake account to proper format for trust policy
# Example: WYHSRGP-QTB42213 -> wyhsrgp-qtb42213.snowflakecomputing.com
SNOWFLAKE_ACCOUNT_LOWER=$(echo "$SNOWFLAKE_ACCOUNT" | tr '[:upper:]' '[:lower:]')
SNOWFLAKE_ACCOUNT_ID="${SNOWFLAKE_ACCOUNT_LOWER}.snowflakecomputing.com"

echo "📋 Snowflake Account ID: $SNOWFLAKE_ACCOUNT_ID"

# Create IAM role for Snowflake
echo "📝 Creating IAM role for Snowflake..."

cat > snowflake-s3-role-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${AWS_ACCOUNT_ID}:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "SNOWFLAKE_S3_INTEGRATION"
        }
      }
    }
  ]
}
EOF

# Create the IAM role
echo "📝 Creating IAM role..."
if aws iam create-role \
  --role-name snowflake-s3-role \
  --assume-role-policy-document file://snowflake-s3-role-trust-policy.json \
  --description "Role for Snowflake S3 integration" 2>/dev/null; then
    echo "✅ IAM role created successfully"
else
    echo "ℹ️  IAM role may already exist, continuing..."
fi

# Create policy for S3 access
echo "📝 Creating S3 access policy..."

cat > snowflake-s3-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET}",
        "arn:aws:s3:::${S3_BUCKET}/*"
      ]
    }
  ]
}
EOF

# Create the policy
echo "📝 Creating IAM policy..."
if aws iam create-policy \
  --policy-name snowflake-s3-policy \
  --policy-document file://snowflake-s3-policy.json 2>/dev/null; then
    echo "✅ IAM policy created successfully"
else
    echo "ℹ️  IAM policy may already exist, continuing..."
fi

# Attach policy to role
echo "📝 Attaching policy to role..."
if aws iam attach-role-policy \
  --role-name snowflake-s3-role \
  --policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/snowflake-s3-policy; then
    echo "✅ Policy attached successfully"
else
    echo "ℹ️  Policy may already be attached"
fi

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name snowflake-s3-role --query Role.Arn --output text)
echo "✅ IAM Role ARN: $ROLE_ARN"

# Clean up temporary files
rm -f snowflake-s3-role-trust-policy.json snowflake-s3-policy.json

echo ""
echo "🎉 AWS IAM setup completed!"
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Add these to your .env file:"
echo "   AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID"
echo "   SNOWFLAKE_S3_ROLE_ARN=$ROLE_ARN"
echo ""
echo "2. In Snowflake console (as ACCOUNTADMIN), run:"
echo "   CREATE OR REPLACE STORAGE INTEGRATION S3_STOCK_INTEGRATION"
echo "   TYPE = EXTERNAL_STAGE"
echo "   STORAGE_PROVIDER = S3"
echo "   ENABLED = TRUE"
echo "   STORAGE_AWS_ROLE_ARN = '$ROLE_ARN'"
echo "   STORAGE_ALLOWED_LOCATIONS = ('s3://${S3_BUCKET}/');"
echo ""
echo "3. Get the integration properties:"
echo "   DESC INTEGRATION S3_STOCK_INTEGRATION;"
echo ""
echo "4. Copy the AWS_IAM_USER_ARN from step 3 and update the trust policy:"
echo "   aws iam update-assume-role-policy \\"
echo "     --role-name snowflake-s3-role \\"
echo "     --policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"<AWS_IAM_USER_ARN_FROM_STEP_3>\"},\"Action\":\"sts:AssumeRole\",\"Condition\":{\"StringEquals\":{\"sts:ExternalId\":\"<STORAGE_INTEGRATION_EXTERNAL_ID>\"}}}]}'"
echo ""
echo "5. Test the integration:"
echo "   LIST @S3_STOCK_STAGE;" 