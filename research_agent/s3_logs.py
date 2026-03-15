import os
import logging
from datetime import datetime
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)

class S3LogUploader:
    def __init__(self):
        """Initialize S3 client for log uploads"""
        try:
            # Get configuration from environment
            self.bucket = os.getenv('S3_BUCKET', 'ava-deals-log')
            self.region = os.getenv('S3_REGION', 'us-east-1')
            
            # Check if AWS credentials are available
            if not os.getenv('AWS_ACCESS_KEY_ID') or not os.getenv('AWS_SECRET_ACCESS_KEY'):
                logger.warning("AWS credentials not configured. Log upload to S3 will be skipped.")
                self.s3 = None
                return
            
            # Initialize S3 client
            self.s3 = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            
            # Test S3 access
            self._test_s3_access()
            logger.info(f"S3 log uploader initialized - Bucket: {self.bucket}")
            
        except NoCredentialsError:
            logger.warning("AWS credentials not found. Log upload to S3 will be skipped.")
            self.s3 = None
        except Exception as e:
            logger.warning(f"Failed to initialize S3 log uploader: {e}. Continuing without S3 uploads.")
            self.s3 = None
    
    def _test_s3_access(self):
        """Test if we can access the S3 bucket"""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                # Try to create the bucket if it doesn't exist
                try:
                    if self.region == 'us-east-1':
                        self.s3.create_bucket(Bucket=self.bucket)
                    else:
                        self.s3.create_bucket(
                            Bucket=self.bucket,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"Created S3 bucket: {self.bucket}")
                except Exception as create_error:
                    logger.warning(f"Could not create S3 bucket '{self.bucket}': {create_error}")
                    raise
            elif error_code == 403:
                logger.warning(f"Access denied to S3 bucket '{self.bucket}'")
                raise
            else:
                logger.warning(f"Error accessing S3 bucket: {e}")
                raise
    
    def _get_content_type(self, filename: str) -> str:
        """Determine content type based on file extension"""
        ext = Path(filename).suffix.lower()
        content_types = {
            '.json': 'application/json',
            '.jsonl': 'application/x-ndjson',
            '.md': 'text/markdown',
            '.log': 'text/plain',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.csv': 'text/csv'
        }
        return content_types.get(ext, 'application/octet-stream')
    
    async def upload_project_logs(self, project_dir: str, handle: str) -> bool:
        """Upload a project's log directory to S3
        
        Args:
            project_dir: Full path to the project directory (e.g., logs/projects_20241227/handle_project)
            handle: Twitter handle or project name
            
        Returns:
            True if upload successful, False otherwise
        """
        # Skip if S3 is not configured
        if not self.s3:
            logger.debug("S3 not configured, skipping log upload")
            return False
        
        try:
            # Check if project directory exists
            if not os.path.exists(project_dir):
                logger.warning(f"Project directory not found: {project_dir}")
                return False
            
            # List all files to upload
            files_to_upload = []
            total_size = 0
            
            for root, _, files in os.walk(project_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        files_to_upload.append((file_path, file, file_size))
                        total_size += file_size
                    except Exception as e:
                        logger.debug(f"Could not access file {file_path}: {e}")
            
            if not files_to_upload:
                logger.warning(f"No files found in project directory: {project_dir}")
                return False
            
            logger.info(f"\n📊 Uploading project logs to S3:")
            logger.info(f"   Handle: {handle}")
            logger.info(f"   Source: {project_dir}")
            logger.info(f"   Files: {len(files_to_upload)}")
            logger.info(f"   Total size: {total_size / 1024 / 1024:.2f} MB")
            
            # Upload each file directly to S3 with handle as prefix
            upload_count = 0
            for file_path, filename, file_size in files_to_upload:
                try:
                    # Simple S3 key: handle/filename
                    s3_key = f"{handle}/{filename}"
                    
                    # Determine content type
                    content_type = self._get_content_type(filename)
                    
                    # Upload metadata
                    metadata = {
                        'handle': handle,
                        'upload-time': datetime.now().isoformat(),
                        'source-machine': os.environ.get('HOSTNAME', os.environ.get('COMPUTERNAME', 'unknown')),
                        'uploaded-by': os.environ.get('USER', 'unknown')
                    }
                    
                    # Upload the file
                    logger.info(f"   Uploading: {filename} ({file_size / 1024:.1f} KB)")
                    self.s3.upload_file(
                        file_path,
                        self.bucket,
                        s3_key,
                        ExtraArgs={
                            'Metadata': metadata,
                            'ContentType': content_type
                        }
                    )
                    upload_count += 1
                    
                except Exception as e:
                    logger.error(f"   Failed to upload {filename}: {e}")
                    # Continue uploading other files even if one fails
            
            if upload_count > 0:
                logger.info(f"\n✅ Successfully uploaded {upload_count}/{len(files_to_upload)} files to S3")
                logger.info(f"   S3 Location: s3://{self.bucket}/{handle}/")
                logger.info(f"   Upload time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                logger.error("Failed to upload any files to S3")
                return False
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchBucket':
                logger.error(f"S3 bucket '{self.bucket}' does not exist")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied when uploading to S3 bucket '{self.bucket}'")
            else:
                logger.error(f"Failed to upload logs to S3: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error uploading logs to S3: {e}")
            return False