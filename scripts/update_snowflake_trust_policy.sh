#!/bin/bash

# Update Snowflake Trust Policy
# This script updates the IAM role trust policy with the correct Snowflake user ARN

set -e

# Load environment variables
source ../.env

echo "🔧 Updating Snowflake Trust Policy..."

# Check if required parameters are provided
if [ $# -ne 2 ]; then
    echo "❌ Usage: $0 <SNOWFLAKE_AWS_IAM_USER_ARN> <STORAGE_INTEGRATION_EXTERNAL_ID>"
    echo ""
    echo "📋 To get these values:"
    echo "1. In Snowflake console, run: DESC INTEGRATION S3_STOCK_INTEGRATION;"
    echo "2. Copy the AWS_IAM_USER_ARN and STORAGE_INTEGRATION_EXTERNAL_ID values"
    echo ""
    echo "Example:"
    echo "  $0 'arn:aws:iam::123456789012:user/snowflake-user' 'SNOWFLAKE_S3_INTEGRATION_12345'"
    exit 1
fi

SNOWFLAKE_AWS_IAM_USER_ARN=$1
STORAGE_INTEGRATION_EXTERNAL_ID=$2

echo "📋 Snowflake AWS IAM User ARN: $SNOWFLAKE_AWS_IAM_USER_ARN"
echo "📋 Storage Integration External ID: $STORAGE_INTEGRATION_EXTERNAL_ID"

# Create the updated trust policy
cat > updated-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "$SNOWFLAKE_AWS_IAM_USER_ARN"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "$STORAGE_INTEGRATION_EXTERNAL_ID"
        }
      }
    }
  ]
}
EOF

echo "📝 Updating IAM role trust policy..."

# Update the role's trust policy
if aws iam update-assume-role-policy \
  --role-name snowflake-s3-role \
  --policy-document file://updated-trust-policy.json; then
    echo "✅ Trust policy updated successfully!"
else
    echo "❌ Failed to update trust policy"
    exit 1
fi

# Clean up
rm -f updated-trust-policy.json

echo ""
echo "🎉 Trust policy update completed!"
echo ""
echo "📋 Next steps:"
echo "1. Test the Snowflake integration:"
echo "   LIST @S3_STOCK_STAGE;"
echo ""
echo "2. If successful, test loading data:"
echo "   COPY INTO STOCK_DATA FROM @S3_STOCK_STAGE/raw/stock-data/year=2025/month=07/day=20/;" 