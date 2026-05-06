import boto3
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
    )

def upload_file_to_s3(file_obj, filename: str, content_type: str) -> str:
    s3 = get_s3_client()
    try:
        s3.upload_fileobj(
            file_obj,
            settings.S3_BUCKET_NAME,
            filename,
            ExtraArgs={"ContentType": content_type}
        )
        # Assuming path-style addressing for generic S3
        return f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET_NAME}/{filename}"
    except ClientError as e:
        logger.error(f"S3 upload error: {e}")
        raise
