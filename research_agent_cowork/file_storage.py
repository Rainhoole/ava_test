#!/usr/bin/env python3
"""
File Storage Layer for Research Agent.

Provides unified file storage with local-first, remote-backup strategy.
Supports AWS S3 compatible storage (Railway Bucket).
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class FileStorage:
    """
    Unified file storage layer.

    - Local-first: All writes go to local filesystem first
    - Remote backup: Sync to S3-compatible bucket after task completion
    - Read fallback: If local file missing, try to fetch from remote
    """

    def __init__(self, base_dir: str = "outputs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

        # AWS S3 compatible configuration
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.endpoint_url = os.getenv("AWS_ENDPOINT_URL")
        self.region = os.getenv("AWS_DEFAULT_REGION", "auto")

        self._s3_client = None
        self._s3_initialized = False

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 storage is configured."""
        return bool(self.bucket_name and self.endpoint_url)

    @property
    def s3_client(self):
        """Lazy-initialize S3 client."""
        if not self._s3_initialized:
            self._s3_initialized = True
            if self.s3_enabled:
                try:
                    import boto3
                    self._s3_client = boto3.client(
                        's3',
                        endpoint_url=self.endpoint_url,
                        region_name=self.region,
                        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    )
                    logger.info(f"S3 client initialized: bucket={self.bucket_name}, endpoint={self.endpoint_url}")
                except ImportError:
                    logger.warning("boto3 not installed, S3 storage disabled")
                except Exception as e:
                    logger.error(f"Failed to initialize S3 client: {e}")
        return self._s3_client

    # ===== Path Helpers =====

    def _get_date_from_task_id(self, task_id: str) -> str:
        """Extract date string from task_id (format: YYYYMMDD_HHMMSS_handle_xxx)."""
        return task_id.split('_')[0]

    def _get_date_dir(self, task_id: str) -> Path:
        """Get local date directory for a task."""
        date_str = self._get_date_from_task_id(task_id)
        return self.base_dir / date_str

    def _get_remote_key(self, task_id: str, filename: str) -> str:
        """Get S3 key for a file: tasks/{date}/{filename}"""
        date_str = self._get_date_from_task_id(task_id)
        return f"tasks/{date_str}/{filename}"

    def get_file_path(self, task_id: str, handle: str, file_type: str) -> Path:
        """
        Get local file path for a task file.

        Args:
            task_id: Task identifier
            handle: Twitter handle (without @)
            file_type: One of 'log', 'jsonl', 'report', 'meta'

        Returns:
            Path to the local file
        """
        clean_handle = handle.replace('@', '')
        date_dir = self._get_date_dir(task_id)

        extensions = {
            'log': '_messages.log',
            'jsonl': '_messages.jsonl',
            'report': '_research.md',
            'meta': '_meta.json'
        }

        suffix = extensions.get(file_type, f'_{file_type}')
        filename = f"{clean_handle}_{task_id}{suffix}"
        return date_dir / filename

    # ===== Write Operations =====

    def write_file(self, task_id: str, filename: str, content: str | bytes) -> Path:
        """
        Write content to local file.

        Args:
            task_id: Task identifier (used to determine date directory)
            filename: File name
            content: File content (str or bytes)

        Returns:
            Path to written file
        """
        date_dir = self._get_date_dir(task_id)
        date_dir.mkdir(parents=True, exist_ok=True)

        file_path = date_dir / filename
        mode = 'wb' if isinstance(content, bytes) else 'w'
        encoding = None if isinstance(content, bytes) else 'utf-8'

        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)

        return file_path

    def create_meta(
        self,
        task_id: str,
        handle: str,
        version: str,
        files: Dict[str, str],
        **extra
    ) -> Path:
        """
        Create meta.json for a task.

        Args:
            task_id: Task identifier
            handle: Twitter handle
            version: Agent version
            files: Dict of file type -> filename
            **extra: Additional metadata fields

        Returns:
            Path to meta.json
        """
        clean_handle = handle.replace('@', '')

        meta = {
            "version": "1.0",
            "task_id": task_id,
            "handle": handle,
            "agent_version": version,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": None,
            "status": "pending",
            "files": files,
            "stats": {
                "message_count": 0,
                "cost_usd": 0.0,
                "duration_seconds": None
            },
            "storage": {
                "local": True,
                "remote": False,
                "remote_synced_at": None
            },
            **extra
        }

        filename = f"{clean_handle}_{task_id}_meta.json"
        return self.write_file(task_id, filename, json.dumps(meta, indent=2, ensure_ascii=False))

    def update_meta(self, task_id: str, handle: str, updates: Dict[str, Any]) -> Optional[Path]:
        """
        Update meta.json with new values.

        Args:
            task_id: Task identifier
            handle: Twitter handle
            updates: Dict of fields to update (supports nested paths like "stats.cost_usd")

        Returns:
            Path to updated meta.json, or None if meta doesn't exist
        """
        meta = self.read_meta(task_id, handle)
        if not meta:
            return None

        # Apply updates (support nested keys like "stats.cost_usd")
        for key, value in updates.items():
            if '.' in key:
                parts = key.split('.')
                obj = meta
                for part in parts[:-1]:
                    obj = obj.setdefault(part, {})
                obj[parts[-1]] = value
            else:
                meta[key] = value

        clean_handle = handle.replace('@', '')
        filename = f"{clean_handle}_{task_id}_meta.json"
        return self.write_file(task_id, filename, json.dumps(meta, indent=2, ensure_ascii=False))

    # ===== Read Operations (Local-First) =====

    def read_file(self, task_id: str, filename: str, encoding: str = 'utf-8') -> Optional[str]:
        """
        Read file content - local first, fallback to remote.

        Args:
            task_id: Task identifier
            filename: File name
            encoding: Text encoding (default utf-8)

        Returns:
            File content or None if not found
        """
        # 1. Try local
        local_path = self._get_date_dir(task_id) / filename
        if local_path.exists():
            return local_path.read_text(encoding=encoding)

        # 2. Try remote
        if self.s3_client:
            try:
                remote_key = self._get_remote_key(task_id, filename)
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=remote_key
                )
                content = response['Body'].read().decode(encoding)

                # Cache to local
                self.write_file(task_id, filename, content)
                logger.info(f"Downloaded from S3 and cached: {filename}")

                return content
            except self.s3_client.exceptions.NoSuchKey:
                logger.debug(f"File not found in S3: {remote_key}")
            except Exception as e:
                logger.error(f"S3 read error: {e}")

        return None

    def read_meta(self, task_id: str, handle: str) -> Optional[Dict]:
        """
        Read meta.json for a task.

        Args:
            task_id: Task identifier
            handle: Twitter handle

        Returns:
            Meta dict or None if not found
        """
        clean_handle = handle.replace('@', '')
        filename = f"{clean_handle}_{task_id}_meta.json"
        content = self.read_file(task_id, filename)

        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse meta.json: {e}")

        return None

    def file_exists_local(self, task_id: str, filename: str) -> bool:
        """Check if file exists locally."""
        local_path = self._get_date_dir(task_id) / filename
        return local_path.exists()

    # ===== Remote Sync Operations =====

    def sync_to_remote(self, task_id: str, handle: str) -> bool:
        """
        Sync all task files to remote S3 bucket.

        Args:
            task_id: Task identifier
            handle: Twitter handle

        Returns:
            True if sync successful, False otherwise
        """
        if not self.s3_client:
            logger.debug("S3 not configured, skipping remote sync")
            return False

        clean_handle = handle.replace('@', '')
        date_dir = self._get_date_dir(task_id)

        if not date_dir.exists():
            logger.warning(f"Output directory not found: {date_dir}")
            return False

        # Find all files for this task
        prefix = f"{clean_handle}_{task_id}_"
        files_synced = 0

        try:
            for file_path in date_dir.glob(f"{prefix}*"):
                if file_path.is_file():
                    remote_key = self._get_remote_key(task_id, file_path.name)

                    # Determine content type
                    content_type = 'application/octet-stream'
                    if file_path.suffix == '.json':
                        content_type = 'application/json'
                    elif file_path.suffix == '.md':
                        content_type = 'text/markdown'
                    elif file_path.suffix in ('.log', '.jsonl', '.txt'):
                        content_type = 'text/plain'

                    self.s3_client.upload_file(
                        str(file_path),
                        self.bucket_name,
                        remote_key,
                        ExtraArgs={'ContentType': content_type}
                    )
                    files_synced += 1
                    logger.debug(f"Uploaded to S3: {remote_key}")

            # Update meta to reflect sync
            if files_synced > 0:
                self.update_meta(task_id, handle, {
                    "storage.remote": True,
                    "storage.remote_synced_at": datetime.utcnow().isoformat() + "Z"
                })
                logger.info(f"Synced {files_synced} files to S3 for task {task_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to sync to S3: {e}")
            return False

    def download_task_from_remote(self, task_id: str, handle: str) -> bool:
        """
        Download all task files from remote to local.

        Args:
            task_id: Task identifier
            handle: Twitter handle

        Returns:
            True if any files downloaded, False otherwise
        """
        if not self.s3_client:
            return False

        clean_handle = handle.replace('@', '')
        date_str = self._get_date_from_task_id(task_id)
        prefix = f"tasks/{date_str}/{clean_handle}_{task_id}_"

        try:
            # List objects with prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                return False

            date_dir = self._get_date_dir(task_id)
            date_dir.mkdir(parents=True, exist_ok=True)

            files_downloaded = 0
            for obj in response['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]
                local_path = date_dir / filename

                if not local_path.exists():
                    self.s3_client.download_file(
                        self.bucket_name,
                        key,
                        str(local_path)
                    )
                    files_downloaded += 1
                    logger.debug(f"Downloaded from S3: {filename}")

            if files_downloaded > 0:
                logger.info(f"Downloaded {files_downloaded} files from S3 for task {task_id}")

            return files_downloaded > 0

        except Exception as e:
            logger.error(f"Failed to download from S3: {e}")
            return False

    def list_remote_tasks(self, date_str: Optional[str] = None) -> List[str]:
        """
        List task IDs available in remote storage.

        Args:
            date_str: Optional date filter (YYYYMMDD)

        Returns:
            List of task IDs
        """
        if not self.s3_client:
            return []

        prefix = f"tasks/{date_str}/" if date_str else "tasks/"
        task_ids = set()

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get('Contents', []):
                    # Extract task_id from key: tasks/YYYYMMDD/handle_TASKID_type.ext
                    key = obj['Key']
                    parts = key.split('/')
                    if len(parts) >= 3:
                        filename = parts[-1]
                        # Parse: handle_YYYYMMDD_HHMMSS_handle_xxx_type.ext
                        # task_id format: YYYYMMDD_HHMMSS_handle_xxx
                        name_parts = filename.rsplit('_', 1)[0]  # Remove _type.ext
                        if '_' in name_parts:
                            # Reconstruct task_id
                            task_ids.add(name_parts.split('_', 1)[1] if '_' in name_parts else name_parts)

            return list(task_ids)

        except Exception as e:
            logger.error(f"Failed to list remote tasks: {e}")
            return []

    def list_all_remote_meta(self) -> List[Dict[str, Any]]:
        """
        List and download all meta.json files from remote storage.

        Returns:
            List of meta dicts with task info
        """
        if not self.s3_client:
            return []

        meta_files = []
        prefix = "tasks/"

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Only process meta.json files
                    if key.endswith('_meta.json'):
                        try:
                            response = self.s3_client.get_object(
                                Bucket=self.bucket_name,
                                Key=key
                            )
                            content = response['Body'].read().decode('utf-8')
                            meta = json.loads(content)
                            meta_files.append(meta)

                            # Cache to local
                            parts = key.split('/')
                            if len(parts) >= 3:
                                filename = parts[-1]
                                task_id = meta.get('task_id', '')
                                if task_id:
                                    self.write_file(task_id, filename, content)
                                    logger.debug(f"Cached meta from S3: {filename}")
                        except Exception as e:
                            logger.warning(f"Failed to download meta {key}: {e}")

            logger.info(f"Found {len(meta_files)} tasks in remote storage")
            return meta_files

        except Exception as e:
            logger.error(f"Failed to list remote meta files: {e}")
            return []

    def download_all_task_files(self, task_id: str, handle: str) -> int:
        """
        Download all files for a task from remote storage.

        Args:
            task_id: Task identifier
            handle: Twitter handle

        Returns:
            Number of files downloaded
        """
        if not self.s3_client:
            return 0

        clean_handle = handle.replace('@', '')
        date_str = self._get_date_from_task_id(task_id)
        prefix = f"tasks/{date_str}/{clean_handle}_{task_id}_"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                return 0

            date_dir = self._get_date_dir(task_id)
            date_dir.mkdir(parents=True, exist_ok=True)

            files_downloaded = 0
            for obj in response['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]
                local_path = date_dir / filename

                # Always overwrite to ensure fresh data from remote
                try:
                    self.s3_client.download_file(
                        self.bucket_name,
                        key,
                        str(local_path)
                    )
                    files_downloaded += 1
                    logger.debug(f"Downloaded from S3: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to download {filename}: {e}")

            return files_downloaded

        except Exception as e:
            logger.error(f"Failed to download task files: {e}")
            return 0


# Global instance
_file_storage: Optional[FileStorage] = None


def get_file_storage(base_dir: str = "outputs") -> FileStorage:
    """Get or create global FileStorage instance."""
    global _file_storage
    if _file_storage is None:
        _file_storage = FileStorage(base_dir)
    return _file_storage
