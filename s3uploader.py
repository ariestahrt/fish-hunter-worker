import boto3
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY=os.getenv("AWS_ACCESS_KEY")
SECRET_KEY=os.getenv("AWS_SECRET_KEY")
BUCKET=os.getenv("AWS_BUCKET")

def compress_and_upload(dataset_path, bucket_filename):
    os.system(f"7z a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on -mhe=on -p'heart123' {bucket_filename} {dataset_path}")
    upload_to_aws(bucket_filename)
    # Remove file
    os.system(f"rm {bucket_filename}")
    # Remove dir
    os.system(f"rm -rf {dataset_path}")

def upload_to_aws(local_file):
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY)

    dest = "datasets/" + local_file

    try:
        s3.upload_file(local_file, BUCKET, dest)
        print("Upload Successful")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False

if __name__ == "__main__":
    None