#!/usr/bin/env python3
"""
Task Manager for Research Agent Web Server.

Manages research tasks with SQLite storage.
"""

import asyncio
import aiosqlite
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, asdict

from file_storage import FileStorage, get_file_storage

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    """Payment status for research tasks."""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    task_id: str
    handle: str
    status: TaskStatus
    version: str
    created_at: str
    client_id: Optional[str] = None
    engine: str = "openai"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_dir: Optional[str] = None
    log_file: Optional[str] = None
    jsonl_file: Optional[str] = None  # Structured JSONL log for frontend
    report_file: Optional[str] = None
    error_message: Optional[str] = None
    message_count: int = 0
    cost_usd: float = 0.0
    # Payment fields
    mandate_id: Optional[str] = None
    fluxa_jwt: Optional[str] = None  # JWT for payment processing
    budget_usd: float = 2.0  # Default budget of $2.00
    payment_status: PaymentStatus = PaymentStatus.PENDING
    payment_amount_usd: float = 0.0  # Actual amount charged
    tool_calls: int = 0  # Number of tool calls for cost calculation
    payment_error: Optional[str] = None
    payment_tx_hash: Optional[str] = None
    # Structured failure fields
    failure_stage: Optional[str] = None      # provider_auth | provider_quota | provider_runtime | tool_runtime | internal
    failure_code: Optional[str] = None       # machine-readable error code
    retryable: Optional[bool] = None         # whether client should retry
    upstream_request_id: Optional[str] = None  # e.g. OpenAI req_xxx
    instant: bool = True  # Use instant processing (disable flex)
    upload_file: Optional[str] = None  # Path to uploaded file (PDF, etc.)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskManager:
    """Manages research tasks with SQLite storage."""

    def __init__(self, db_path: str = "tasks.db", output_base: str = "outputs"):
        self.db_path = Path(db_path)
        self.output_base = Path(output_base)
        self._db: Optional[aiosqlite.Connection] = None
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self.file_storage = get_file_storage(str(output_base))

    async def init(self):
        """Initialize database."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                handle TEXT NOT NULL,
                client_id TEXT,
                status TEXT NOT NULL,
                version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                engine TEXT DEFAULT 'claude',
                started_at TEXT,
                completed_at TEXT,
                output_dir TEXT,
                log_file TEXT,
                jsonl_file TEXT,
                report_file TEXT,
                error_message TEXT,
                message_count INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                mandate_id TEXT,
                fluxa_jwt TEXT,
                budget_usd REAL DEFAULT 2.0,
                payment_status TEXT DEFAULT 'pending',
                payment_amount_usd REAL DEFAULT 0.0,
                tool_calls INTEGER DEFAULT 0,
                payment_error TEXT,
                payment_tx_hash TEXT
            )
        """)

        # Migration: add jsonl_file column if not exists
        try:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN jsonl_file TEXT")
        except:
            pass  # Column already exists

        # Migration: add engine column
        try:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN engine TEXT DEFAULT 'claude'")
        except:
            pass  # Column already exists

        # Migration: add client_id column
        try:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN client_id TEXT")
        except:
            pass  # Column already exists

        # Migration: add payment-related columns
        payment_columns = [
            ("mandate_id", "TEXT"),
            ("fluxa_jwt", "TEXT"),
            ("budget_usd", "REAL DEFAULT 2.0"),
            ("payment_status", "TEXT DEFAULT 'pending'"),
            ("payment_amount_usd", "REAL DEFAULT 0.0"),
            ("tool_calls", "INTEGER DEFAULT 0"),
            ("payment_error", "TEXT"),
            ("payment_tx_hash", "TEXT"),
        ]
        for col_name, col_type in payment_columns:
            try:
                await self._db.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
            except:
                pass  # Column already exists

        # Migration: add structured failure columns
        failure_columns = [
            ("failure_stage", "TEXT"),
            ("failure_code", "TEXT"),
            ("retryable", "INTEGER"),
            ("upstream_request_id", "TEXT"),
        ]
        for col_name, col_type in failure_columns:
            try:
                await self._db.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
            except:
                pass  # Column already exists

        # Migration: add instant column
        try:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN instant INTEGER DEFAULT 0")
        except:
            pass  # Column already exists

        # Migration: add upload_file column
        try:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN upload_file TEXT")
        except:
            pass  # Column already exists

        # Backfill legacy rows: if no mandate, payment should be skipped (not pending)
        try:
            await self._db.execute(
                """
                UPDATE tasks
                SET payment_status = ?
                WHERE (payment_status IS NULL OR payment_status = '' OR payment_status = 'pending')
                  AND (mandate_id IS NULL OR mandate_id = '')
                """,
                (PaymentStatus.SKIPPED.value,)
            )
        except Exception as e:
            logger.debug(f"Payment status backfill skipped: {e}")

        await self._db.commit()

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()

    @staticmethod
    def _clean_handle_for_fs(handle: str) -> str:
        """Extract a filesystem-safe name from a handle or URL."""
        import re
        if handle.startswith('http://') or handle.startswith('https://'):
            from urllib.parse import urlparse
            parsed = urlparse(handle)
            domain = parsed.netloc.replace('www.', '').split('.')[0]
            path_parts = [p for p in parsed.path.strip('/').split('/') if p]
            name = path_parts[-1][:30] if path_parts else domain
            return re.sub(r'[^\w-]', '_', name)[:40] or 'research'
        return handle.replace('@', '')

    def _generate_task_id(self, handle: str) -> str:
        """Generate unique task ID."""
        clean_handle = self._clean_handle_for_fs(handle)
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"{date_str}_{clean_handle}_{short_uuid}"

    async def create_task(
        self,
        handle: str,
        version: str,
        engine: str = "openai",
        client_id: Optional[str] = None,
        mandate_id: Optional[str] = None,
        budget_usd: float = 2.0,
        fluxa_jwt: Optional[str] = None,
        instant: bool = True,
        upload_file: Optional[str] = None
    ) -> Task:
        """Create a new research task with optional payment info."""
        task_id = self._generate_task_id(handle)
        clean_handle = self._clean_handle_for_fs(handle)

        # Create output directory
        date_dir = datetime.now().strftime("%Y%m%d")
        output_dir = self.output_base / date_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # File paths (dual logging: .log for humans, .jsonl for frontend)
        log_file = output_dir / f"{clean_handle}_{task_id}_messages.log"
        jsonl_file = output_dir / f"{clean_handle}_{task_id}_messages.jsonl"
        report_file = output_dir / f"{clean_handle}_{task_id}_research.md"
        meta_file = output_dir / f"{clean_handle}_{task_id}_meta.json"

        # Determine initial payment status
        payment_status = PaymentStatus.AUTHORIZED if mandate_id else PaymentStatus.SKIPPED

        task = Task(
            task_id=task_id,
            handle=handle,
            client_id=client_id,
            status=TaskStatus.PENDING,
            version=version,
            created_at=datetime.now().isoformat(),
            engine=engine,
            output_dir=str(output_dir),
            log_file=str(log_file),
            jsonl_file=str(jsonl_file),
            report_file=str(report_file),
            mandate_id=mandate_id,
            fluxa_jwt=fluxa_jwt,
            budget_usd=budget_usd,
            payment_status=payment_status,
            instant=instant,
            upload_file=upload_file
        )

        await self._db.execute("""
            INSERT INTO tasks (
                task_id, handle, client_id, status, version, created_at, engine,
                output_dir, log_file, jsonl_file, report_file,
                mandate_id, fluxa_jwt, budget_usd, payment_status, instant, upload_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id, task.handle, task.client_id, task.status.value, task.version,
            task.created_at, task.engine, task.output_dir, task.log_file,
            task.jsonl_file, task.report_file,
            task.mandate_id, task.fluxa_jwt, task.budget_usd, task.payment_status.value,
            int(task.instant), task.upload_file
        ))
        await self._db.commit()

        # Create meta.json for the task
        try:
            self.file_storage.create_meta(
                task_id=task_id,
                handle=handle,
                version=version,
                files={
                    "log": log_file.name,
                    "jsonl": jsonl_file.name,
                    "report": report_file.name,
                    "meta": meta_file.name
                },
                client_id=client_id,
                engine=engine,
                mandate_id=mandate_id,
                budget_usd=budget_usd,
                payment_status=payment_status.value,
                payment_amount_usd=0.0
            )
            logger.debug(f"Created meta.json for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to create meta.json: {e}")

        return task

    def _get_payment_status(self, value: Optional[str]) -> PaymentStatus:
        """Safely get PaymentStatus from string value."""
        if not value:
            return PaymentStatus.PENDING
        try:
            return PaymentStatus(value)
        except ValueError:
            return PaymentStatus.PENDING

    def _count_tool_calls_from_jsonl(self, jsonl_path: Optional[str]) -> int:
        """Count tool_call entries in a JSONL log file."""
        if not jsonl_path:
            return 0
        path = Path(jsonl_path)
        if not path.exists():
            return 0
        count = 0
        try:
            with path.open('r', encoding='utf-8') as handle:
                for line in handle:
                    if '"type": "tool_call"' in line or '"type":"tool_call"' in line:
                        count += 1
        except Exception as e:
            logger.debug(f"Failed to count tool calls from {path}: {e}")
        return count

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        async with self._db.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                keys = row.keys()
                return Task(
                    task_id=row['task_id'],
                    handle=row['handle'],
                    client_id=row['client_id'] if 'client_id' in keys else None,
                    status=TaskStatus(row['status']),
                    version=row['version'],
                    created_at=row['created_at'],
                    engine=row['engine'] if 'engine' in keys else 'openai',
                    started_at=row['started_at'],
                    completed_at=row['completed_at'],
                    output_dir=row['output_dir'],
                    log_file=row['log_file'],
                    jsonl_file=row['jsonl_file'] if 'jsonl_file' in keys else None,
                    report_file=row['report_file'],
                    error_message=row['error_message'],
                    message_count=row['message_count'],
                    cost_usd=row['cost_usd'],
                    mandate_id=row['mandate_id'] if 'mandate_id' in keys else None,
                    fluxa_jwt=row['fluxa_jwt'] if 'fluxa_jwt' in keys else None,
                    budget_usd=row['budget_usd'] if 'budget_usd' in keys else 2.0,
                    payment_status=self._get_payment_status(row['payment_status'] if 'payment_status' in keys else None),
                    payment_amount_usd=row['payment_amount_usd'] if 'payment_amount_usd' in keys else 0.0,
                    tool_calls=row['tool_calls'] if 'tool_calls' in keys else 0,
                    payment_error=row['payment_error'] if 'payment_error' in keys else None,
                    payment_tx_hash=row['payment_tx_hash'] if 'payment_tx_hash' in keys else None,
                    failure_stage=row['failure_stage'] if 'failure_stage' in keys else None,
                    failure_code=row['failure_code'] if 'failure_code' in keys else None,
                    retryable=bool(row['retryable']) if 'retryable' in keys and row['retryable'] is not None else None,
                    upstream_request_id=row['upstream_request_id'] if 'upstream_request_id' in keys else None,
                    instant=bool(row['instant']) if 'instant' in keys and row['instant'] else False,
                    upload_file=row['upload_file'] if 'upload_file' in keys else None
                )
            return None

    async def list_tasks(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[TaskStatus] = None,
        client_id: Optional[str] = None
    ) -> List[Task]:
        """List tasks with pagination."""
        query = "SELECT * FROM tasks"
        params = []

        filters = []
        if status:
            filters.append("status = ?")
            params.append(status.value)
        if client_id:
            filters.append("client_id = ?")
            params.append(client_id)
        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        tasks = []
        async with self._db.execute(query, params) as cursor:
            async for row in cursor:
                keys = row.keys()
                tasks.append(Task(
                    task_id=row['task_id'],
                    handle=row['handle'],
                    client_id=row['client_id'] if 'client_id' in keys else None,
                    status=TaskStatus(row['status']),
                    version=row['version'],
                    created_at=row['created_at'],
                    engine=row['engine'] if 'engine' in keys else 'openai',
                    started_at=row['started_at'],
                    completed_at=row['completed_at'],
                    output_dir=row['output_dir'],
                    log_file=row['log_file'],
                    jsonl_file=row['jsonl_file'] if 'jsonl_file' in keys else None,
                    report_file=row['report_file'],
                    error_message=row['error_message'],
                    message_count=row['message_count'],
                    cost_usd=row['cost_usd'],
                    mandate_id=row['mandate_id'] if 'mandate_id' in keys else None,
                    fluxa_jwt=row['fluxa_jwt'] if 'fluxa_jwt' in keys else None,
                    budget_usd=row['budget_usd'] if 'budget_usd' in keys else 2.0,
                    payment_status=self._get_payment_status(row['payment_status'] if 'payment_status' in keys else None),
                    payment_amount_usd=row['payment_amount_usd'] if 'payment_amount_usd' in keys else 0.0,
                    tool_calls=row['tool_calls'] if 'tool_calls' in keys else 0,
                    payment_error=row['payment_error'] if 'payment_error' in keys else None,
                    payment_tx_hash=row['payment_tx_hash'] if 'payment_tx_hash' in keys else None,
                    failure_stage=row['failure_stage'] if 'failure_stage' in keys else None,
                    failure_code=row['failure_code'] if 'failure_code' in keys else None,
                    retryable=bool(row['retryable']) if 'retryable' in keys and row['retryable'] is not None else None,
                    upstream_request_id=row['upstream_request_id'] if 'upstream_request_id' in keys else None,
                    instant=bool(row['instant']) if 'instant' in keys and row['instant'] else False,
                    upload_file=row['upload_file'] if 'upload_file' in keys else None
                ))
        return tasks

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
        failure_stage: Optional[str] = None,
        failure_code: Optional[str] = None,
        retryable: Optional[bool] = None,
        upstream_request_id: Optional[str] = None
    ):
        """Update task status with optional structured failure info."""
        now = datetime.now().isoformat()

        if status == TaskStatus.PENDING:
            # Reset for retry: clear error fields and timestamps
            await self._db.execute(
                """UPDATE tasks SET status = ?, started_at = NULL, completed_at = NULL,
                   error_message = ?, failure_stage = ?, failure_code = ?,
                   retryable = ?, upstream_request_id = ?
                   WHERE task_id = ?""",
                (status.value, error_message,
                 failure_stage, failure_code,
                 int(retryable) if retryable is not None else None,
                 upstream_request_id, task_id)
            )
        elif status == TaskStatus.RUNNING:
            await self._db.execute(
                "UPDATE tasks SET status = ?, started_at = ? WHERE task_id = ?",
                (status.value, now, task_id)
            )
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            await self._db.execute(
                """UPDATE tasks SET status = ?, completed_at = ?, error_message = ?,
                   failure_stage = ?, failure_code = ?, retryable = ?, upstream_request_id = ?
                   WHERE task_id = ?""",
                (status.value, now, error_message,
                 failure_stage, failure_code,
                 int(retryable) if retryable is not None else None,
                 upstream_request_id, task_id)
            )
        else:
            await self._db.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (status.value, task_id)
            )
        await self._db.commit()

    async def update_task_progress(
        self,
        task_id: str,
        message_count: int,
        cost_usd: float = 0.0,
        tool_calls: Optional[int] = None
    ):
        """Update task progress."""
        if tool_calls is not None:
            await self._db.execute(
                "UPDATE tasks SET message_count = ?, cost_usd = ?, tool_calls = ? WHERE task_id = ?",
                (message_count, cost_usd, tool_calls, task_id)
            )
        else:
            await self._db.execute(
                "UPDATE tasks SET message_count = ?, cost_usd = ? WHERE task_id = ?",
                (message_count, cost_usd, task_id)
            )
        await self._db.commit()

        # Best-effort meta update for progress stats
        try:
            updates = {
                "stats.message_count": message_count,
                "stats.cost_usd": cost_usd
            }
            if tool_calls is not None:
                updates["stats.tool_calls"] = tool_calls
            task = await self.get_task(task_id)
            if task:
                self.file_storage.update_meta(task_id, task.handle, updates)
        except Exception as e:
            logger.debug(f"Failed to update meta progress for {task_id}: {e}")

    async def backfill_tool_calls(self, task: Task) -> int:
        """Best-effort tool call count from JSONL logs."""
        tool_calls = self._count_tool_calls_from_jsonl(task.jsonl_file)
        if tool_calls and tool_calls != task.tool_calls:
            await self.update_task_progress(task.task_id, task.message_count, task.cost_usd, tool_calls)
            task.tool_calls = tool_calls
        return tool_calls

    async def update_task_mandate(
        self,
        task_id: str,
        mandate_id: str,
        fluxa_jwt: Optional[str] = None
    ):
        """Update mandate_id (and optionally fluxa_jwt) on a task for payment retry."""
        if fluxa_jwt:
            await self._db.execute(
                "UPDATE tasks SET mandate_id = ?, fluxa_jwt = ? WHERE task_id = ?",
                (mandate_id, fluxa_jwt, task_id)
            )
        else:
            await self._db.execute(
                "UPDATE tasks SET mandate_id = ? WHERE task_id = ?",
                (mandate_id, task_id)
            )
        await self._db.commit()

    async def update_payment_status(
        self,
        task_id: str,
        payment_status: PaymentStatus,
        payment_amount_usd: Optional[float] = None,
        payment_error: Optional[str] = None,
        payment_tx_hash: Optional[str] = None
    ):
        """Update payment status and related fields."""
        updates = ["payment_status = ?"]
        params = [payment_status.value]

        if payment_amount_usd is not None:
            updates.append("payment_amount_usd = ?")
            params.append(payment_amount_usd)
        if payment_error is not None:
            updates.append("payment_error = ?")
            params.append(payment_error)
        if payment_tx_hash is not None:
            updates.append("payment_tx_hash = ?")
            params.append(payment_tx_hash)

        params.append(task_id)
        await self._db.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
            params
        )
        await self._db.commit()

        # Best-effort meta update for payment info
        try:
            updates_meta = {"payment_status": payment_status.value}
            if payment_amount_usd is not None:
                updates_meta["payment_amount_usd"] = payment_amount_usd
            if payment_error is not None:
                updates_meta["payment_error"] = payment_error
            if payment_tx_hash is not None:
                updates_meta["payment_tx_hash"] = payment_tx_hash
            task = await self.get_task(task_id)
            if task:
                self.file_storage.update_meta(task_id, task.handle, updates_meta)
        except Exception as e:
            logger.debug(f"Failed to update meta payment for {task_id}: {e}")

    async def update_task_files(
        self,
        task_id: str,
        log_file: Optional[str] = None,
        jsonl_file: Optional[str] = None,
        report_file: Optional[str] = None
    ):
        """Update task file paths."""
        updates = []
        params = []

        if log_file:
            updates.append("log_file = ?")
            params.append(log_file)
        if jsonl_file:
            updates.append("jsonl_file = ?")
            params.append(jsonl_file)
        if report_file:
            updates.append("report_file = ?")
            params.append(report_file)

        if updates:
            params.append(task_id)
            await self._db.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
                params
            )
            await self._db.commit()

    def register_running_task(self, task_id: str, async_task: asyncio.Task):
        """Register an asyncio task for tracking."""
        self._running_tasks[task_id] = async_task

    def unregister_running_task(self, task_id: str):
        """Unregister a completed asyncio task."""
        self._running_tasks.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            await self.update_task_status(task_id, TaskStatus.CANCELLED)
            self.unregister_running_task(task_id)
            return True
        return False

    def is_task_running(self, task_id: str) -> bool:
        """Check if task is currently running."""
        return task_id in self._running_tasks

    async def sync_task_to_remote(self, task_id: str) -> bool:
        """
        Sync task files to remote storage.

        Args:
            task_id: Task identifier

        Returns:
            True if sync successful
        """
        task = await self.get_task(task_id)
        if not task:
            logger.warning(f"Task not found for sync: {task_id}")
            return False

        return self.file_storage.sync_to_remote(task_id, task.handle)

    def update_task_meta(
        self,
        task_id: str,
        handle: str,
        status: Optional[str] = None,
        message_count: Optional[int] = None,
        cost_usd: Optional[float] = None,
        duration_seconds: Optional[float] = None,
        completed_at: Optional[str] = None,
        error: Optional[str] = None
    ):
        """
        Update task meta.json with current stats.

        Args:
            task_id: Task identifier
            handle: Twitter handle
            status: Task status
            message_count: Number of messages
            cost_usd: Total cost
            duration_seconds: Task duration
            completed_at: Completion timestamp
            error: Error message if failed
        """
        updates = {}

        if status is not None:
            updates["status"] = status
        if completed_at is not None:
            updates["completed_at"] = completed_at
        if error is not None:
            updates["error"] = error
        if message_count is not None:
            updates["stats.message_count"] = message_count
        if cost_usd is not None:
            updates["stats.cost_usd"] = cost_usd
        if duration_seconds is not None:
            updates["stats.duration_seconds"] = duration_seconds

        if updates:
            try:
                self.file_storage.update_meta(task_id, handle, updates)
            except Exception as e:
                logger.error(f"Failed to update meta.json: {e}")

    async def sync_tasks_from_remote(self, download_files: bool = True) -> int:
        """
        Sync tasks from remote bucket storage to local database.

        This should be called on startup to restore task history after redeployment.

        Args:
            download_files: If True, also download all task files (log, report, etc.)

        Returns:
            Number of tasks synced
        """
        if not self.file_storage.s3_enabled:
            logger.info("S3 not configured, skipping remote sync")
            return 0

        logger.info("Starting task sync from remote bucket...")

        # Get all meta files from remote
        remote_metas = self.file_storage.list_all_remote_meta()
        if not remote_metas:
            logger.info("No tasks found in remote storage")
            return 0

        synced_count = 0
        for meta in remote_metas:
            task_id = meta.get('task_id')
            handle = meta.get('handle')

            if not task_id or not handle:
                logger.warning(f"Invalid meta data: {meta}")
                continue

            # Check if task already exists in local DB
            existing = await self.get_task(task_id)
            if existing:
                logger.debug(f"Task already exists locally: {task_id}")
                continue

            # Extract data from meta
            clean_handle = handle.replace('@', '')
            date_str = task_id.split('_')[0]
            output_dir = self.output_base / date_str

            files = meta.get('files', {})
            stats = meta.get('stats', {})
            status_str = meta.get('status', 'completed')
            client_id = meta.get('client_id')
            engine = meta.get('engine')
            mandate_id = meta.get('mandate_id')
            budget_usd = meta.get('budget_usd', 2.0)
            payment_status_str = meta.get('payment_status')
            payment_amount_usd = meta.get('payment_amount_usd', 0.0)
            payment_error = meta.get('payment_error')
            payment_tx_hash = meta.get('payment_tx_hash')
            tool_calls = stats.get('tool_calls', meta.get('tool_calls', 0))

            # Map status string to TaskStatus
            status_map = {
                'pending': TaskStatus.PENDING,
                'running': TaskStatus.COMPLETED,  # Treat stale running as completed
                'completed': TaskStatus.COMPLETED,
                'failed': TaskStatus.FAILED,
                'cancelled': TaskStatus.CANCELLED
            }
            status = status_map.get(status_str, TaskStatus.COMPLETED)

            # Build file paths
            log_file = str(output_dir / files.get('log', f'{clean_handle}_{task_id}_messages.log'))
            jsonl_file = str(output_dir / files.get('jsonl', f'{clean_handle}_{task_id}_messages.jsonl'))
            report_file = str(output_dir / files.get('report', f'{clean_handle}_{task_id}_research.md'))

            # Download all task files if requested
            if download_files:
                files_downloaded = self.file_storage.download_all_task_files(task_id, handle)
                logger.debug(f"Downloaded {files_downloaded} files for task {task_id}")

            # Best-effort tool call count from JSONL (if available)
            if not tool_calls:
                tool_calls = self._count_tool_calls_from_jsonl(jsonl_file)

            # Infer engine from version string (OpenAI models start with gpt/o)
            version_value = meta.get('agent_version', 'v3')
            if not engine:
                engine = "openai"

            payment_status = self._get_payment_status(payment_status_str) if payment_status_str else PaymentStatus.SKIPPED

            # Insert into database
            try:
                await self._db.execute("""
                    INSERT INTO tasks (
                        task_id, handle, client_id, status, version, created_at,
                        started_at, completed_at, output_dir, log_file, jsonl_file,
                        report_file, error_message, message_count, cost_usd,
                        engine, tool_calls, payment_status, budget_usd,
                        payment_amount_usd, payment_error, payment_tx_hash, mandate_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id,
                    handle,
                    client_id,
                    status.value,
                    version_value,
                    meta.get('created_at', ''),
                    meta.get('created_at'),  # Use created_at as started_at
                    meta.get('completed_at'),
                    str(output_dir),
                    log_file,
                    jsonl_file,
                    report_file,
                    meta.get('error'),
                    stats.get('message_count', 0),
                    stats.get('cost_usd', 0.0),
                    engine,
                    tool_calls,
                    payment_status.value,
                    budget_usd,
                    payment_amount_usd,
                    payment_error,
                    payment_tx_hash,
                    mandate_id
                ))
                synced_count += 1
                logger.debug(f"Synced task from remote: {task_id}")
            except Exception as e:
                logger.warning(f"Failed to insert task {task_id}: {e}")

        await self._db.commit()
        logger.info(f"Synced {synced_count} tasks from remote bucket")
        return synced_count
