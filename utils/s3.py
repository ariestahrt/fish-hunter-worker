import boto3
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY=os.getenv("AWS_ACCESS_KEY")
SECRET_KEY=os.getenv("AWS_SECRET_KEY")
PASSWORD=os.getenv("7Z_PASSWORD")

def compress_and_upload(dataset_path, bucket_filename):
    os.system(f"7z a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on -mhe=on -p'{PASSWORD}' {bucket_filename} {dataset_path}")
    upload_file(bucket_filename)
    # Remove file
    os.system(f"rm {bucket_filename}")
    # Remove dir
    os.system(f"rm -rf {dataset_path}")

def upload_file(local_file):
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
    dest = "datasets/" + local_file

    try:
        s3.upload_file(local_file, os.getenv("AWS_BUCKET_DATASET"), dest)
        print("Upload Successful")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False

'''
    Uploads a file to S3
    return True if successful
'''
def upload_image(bucket, local_file, dest):
    # Note: This is only for images
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)

    try:
        s3.upload_file(local_file, bucket, dest, ExtraArgs={'ContentType': 'image/jpg'})
        print("File uploaded successfully")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False

def SevenZIPCompress(compressed_file_path, folder_path):
    folder_path = os.path.abspath(folder_path)
    compressed_file_path = os.path.abspath(compressed_file_path)

    command = f"7z a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on -mhe=on -p\"{os.getenv('7Z_PASSWORD')}\" {compressed_file_path} {folder_path}/*"
    os.system(command)

def upload_file2(bucket, local_file, dest):
    print("Uploading file to S3")
    # Note: This is only for images
    s3 = boto3.client('s3', aws_access_key_id=os.getenv("AWS_ACCESS_KEY"), aws_secret_access_key=os.getenv("AWS_SECRET_KEY"))

    try:
        s3.upload_file(local_file, bucket, dest)
        print("File uploaded successfully")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False


if __name__ == "__main__":
    None