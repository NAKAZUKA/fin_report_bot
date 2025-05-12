from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import os
from loguru import logger

load_dotenv()

MINIO_BUCKET = os.getenv("MINIO_BUCKET", "reports")

client = Minio(
    endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False,
)

def ensure_bucket():
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        logger.info(f"🪣 Bucket `{MINIO_BUCKET}` создан")

def upload_file(file_bytes: bytes, filename: str) -> str:
    ensure_bucket()
    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=filename,
        data=bytes(file_bytes),
        length=len(file_bytes),
        content_type="application/pdf"
    )
    url = f"http://{client._endpoint}/{MINIO_BUCKET}/{filename}"
    logger.info(f"📁 Файл загружен в MinIO: {url}")
    return url
