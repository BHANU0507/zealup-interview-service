import boto3
import os
from botocore.config import Config

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
    config=Config(read_timeout=60)
)

MODEL_ID = os.getenv("MODEL_ID")  # start cheap


def call_bedrock(prompt: str, max_tokens=80, temperature=0.2):

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature
        }
    )

    content_list = response["output"]["message"]["content"]

    for content in content_list:
        if "text" in content:
            return content["text"]

    return ""
