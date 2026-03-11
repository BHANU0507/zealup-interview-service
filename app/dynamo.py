import os
import boto3
from dotenv import load_dotenv

# Load .env file
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE")
DYNAMODB_TABLE2 = os.getenv("DYNAMODB_TABLE2")
DYNAMODB_TABLE3 = os.getenv("DYNAMODB_TABLE3")
DYNAMODB_TABLE4 = os.getenv("DYNAMODB_TABLE4")

# Create DynamoDB resource
dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

table = dynamodb.Table(DYNAMODB_TABLE)

table1 =dynamodb.Table(DYNAMODB_TABLE2)

table2 = dynamodb.Table(DYNAMODB_TABLE3)

table3 = dynamodb.Table(DYNAMODB_TABLE4)
