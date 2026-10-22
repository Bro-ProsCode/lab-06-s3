#!/usr/bin/env python3
"""Download books, create a public S3 bucket, and upload the books and index page."""
import json
import logging
import os
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# One shared S3 client for all functions
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Return (list_file, index_path, bucket) from the command line."""
    if len(sys.argv) < 4:
        log.error("Usage: stage_books.py <book_list> <index.html> <bucket_name>")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download each book URL in list_file into dest_dir; return the local paths."""
    os.makedirs(dest_dir, exist_ok=True)
    paths = []
    with open(list_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        path = os.path.join(dest_dir, os.path.basename(url))
        if os.path.exists(path):
            log.info(f"Skipping (already downloaded): {path}")
            paths.append(path)
            continue
        log.info(f"Downloading {url} to {path}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as book_file:
                book_file.write(response.content)
            paths.append(path)
        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
        time.sleep(1)  # be polite to Project Gutenberg's servers
    return paths


def create_bucket(bucket):
    """Create the bucket if it doesn't exist; return True if it exists afterwards."""
    try:
        s3.head_bucket(Bucket=bucket)  # succeeds only if it exists and we can access it
        log.info(f"Bucket already exists: {bucket}")
        return True
    except ClientError:
        pass  # doesn't exist (or isn't accessible); try to create it

    try:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    """Turn off Block Public Access and attach a public-read bucket policy."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }
        ],
    }
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info(f"Bucket {bucket} successfully made public")
        return True
    except ClientError as e:
        log.error(f"Error making {bucket} public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Upload each file to the top level of the bucket; return the success count."""
    count = 0
    for path in file_paths:
        key = os.path.basename(path)  # e.g. pg1342.txt, not books/pg1342.txt
        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",  # display, not download
                )
            log.info(f"Uploaded {path} to s3://{bucket}/{key}")
            count += 1
        except FileNotFoundError:
            log.error(f"Local file not found: {path}")
        except ClientError as e:
            log.error(f"Error uploading {path}: {e}")
    return count


def upload_index(bucket, index_path):
    """Upload the index page as index.html; return True on success."""
    try:
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=f,
                ContentType="text/html",  # so browsers render it as a page
            )
        log.info(f"Uploaded {index_path} to s3://{bucket}/index.html")
        return True
    except FileNotFoundError:
        log.error(f"Local file not found: {index_path}")
    except ClientError as e:
        log.error(f"Error uploading index: {e}")
    return False


def main():
    """Run all steps in order."""
    list_file, index_path, bucket = parse_args()

    paths = download_books(list_file, "books")
    if not paths:
        log.error("No books were downloaded")
        sys.exit(1)

    if not create_bucket(bucket):
        sys.exit(1)
    if not make_public(bucket):
        sys.exit(1)

    uploaded = upload_files(bucket, paths)
    index_ok = upload_index(bucket, index_path)

    if index_ok and uploaded == len(paths):
        log.info("Everything worked!")
    else:
        log.error(f"Finished with problems: {uploaded}/{len(paths)} books uploaded, "
                  f"index uploaded: {index_ok}")
    log.info(f"The public bucket is at: https://{bucket}.s3.amazonaws.com/index.html")


if __name__ == "__main__":
    main()