#!/bin/bash
# Download one book, upload it to a private bucket, and print a presigned URL.
set -euo pipefail

# Validate positional arguments
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <book_url> <bucket_name> <expiration_seconds>" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
EXPIRES="$3"
FILE="$(basename "$URL")"

# Download the book into books/, keeping the file name from the URL
mkdir -p books
curl -kfL "$URL" -o "books/$FILE"

# Create the bucket unless it already exists
if ! aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    aws s3 mb "s3://$BUCKET"
fi

# Upload the book (bucket and object stay private)
aws s3 cp "books/$FILE" "s3://$BUCKET/$FILE" --content-type "text/plain; charset=utf-8"

# Print a presigned URL that expires after the given number of seconds
aws s3 presign "s3://$BUCKET/$FILE" --expires-in "$EXPIRES"