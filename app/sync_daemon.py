"""
BengkelStack Edge-to-Cloud Sync Daemon
Zero external dependencies: 100% Python standard library.
Extracts completed work orders from local SQLite WAL, signs requests with
HMAC-SHA256, and pushes delta batches to the cloud gateway with automatic
offline buffering and exponential backoff.
"""
import sqlite3
import json
import time
import secrets
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from app.tier2_auth import sign_sync_request


def get_unsynced_work_orders(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    # ponytail: clean index query joining vehicles and motor_models
    cur = conn.cursor()
    cur.execute(
        """
        SELECT wo.id, wo.status, wo.total_amount, wo.payment_method, wo.cash_received, wo.change_amount,
               wo.idempotency_key, wo.created_at, v.plate_number, v.customer_name, m.brand, m.model_name
        FROM work_orders wo
        JOIN vehicles v ON wo.vehicle_id = v.id
        JOIN motor_models m ON v.motor_model_id = m.id
        WHERE wo.synced_to_cloud = 0 AND wo.status = 'COMPLETED'
        ORDER BY wo.id ASC
        LIMIT ?;
        """,
        (limit,)
    )
    return [dict(row) for row in cur.fetchall()]


def mark_orders_as_synced(conn: sqlite3.Connection, order_ids: List[int]) -> None:
    if not order_ids:
        return
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in order_ids)
    cur.execute(
        f"""
        UPDATE work_orders
        SET synced_to_cloud = 1, cloud_synced_at = ?
        WHERE id IN ({placeholders});
        """,
        [now_iso] + order_ids
    )
    conn.commit()


def build_sync_packet(
    tenant_id: int,
    device_id: str,
    device_secret: str,
    orders: List[Dict[str, Any]],
    target_path: str = "/api/v1/sync/push"
) -> Dict[str, Any]:
    timestamp = int(time.time())
    nonce = f"nonce_{secrets.token_hex(8)}"
    payload = {
        "tenant_id": tenant_id,
        "device_id": device_id,
        "timestamp": timestamp,
        "batch_count": len(orders),
        "orders": orders
    }
    body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = sign_sync_request(
        device_secret=device_secret,
        method="POST",
        path=target_path,
        timestamp=timestamp,
        nonce=nonce,
        body=body_bytes
    )

    headers = {
        "Content-Type": "application/json",
        "X-Bengkel-Tenant-Id": str(tenant_id),
        "X-Bengkel-Device-Id": device_id,
        "X-Bengkel-Timestamp": str(timestamp),
        "X-Bengkel-Nonce": nonce,
        "X-Bengkel-Signature": signature
    }

    return {
        "headers": headers,
        "body_bytes": body_bytes,
        "payload": payload
    }


class EdgeSyncDaemon:
    def __init__(
        self,
        db_path: str,
        tenant_id: int,
        device_id: str,
        device_secret: str,
        cloud_url: str = "https://api.bengkelstack.com/v1/sync/push",
        sync_interval: float = 15.0
    ):
        self.db_path = db_path
        self.tenant_id = tenant_id
        self.device_id = device_id
        self.device_secret = device_secret
        self.cloud_url = cloud_url
        self.sync_interval = sync_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.is_connected = False
        self.last_sync_time: Optional[float] = None
        self.backoff_delay = sync_interval

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="EdgeSyncWorker")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def sync_once(self) -> Tuple[bool, int]:
        # Connect to local SQLite
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            orders = get_unsynced_work_orders(conn, limit=50)
            if not orders:
                return True, 0

            target_path = "/api/v1/sync/push"
            packet = build_sync_packet(
                self.tenant_id, self.device_id, self.device_secret, orders, target_path=target_path
            )

            req = urllib.request.Request(
                self.cloud_url,
                data=packet["body_bytes"],
                headers=packet["headers"],
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status in (200, 201):
                    order_ids = [o["id"] for o in orders]
                    mark_orders_as_synced(conn, order_ids)
                    self.is_connected = True
                    self.last_sync_time = time.time()
                    self.backoff_delay = self.sync_interval
                    return True, len(orders)
                else:
                    return False, 0
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            # Offline environment: gracefully buffer locally without crashing
            self.is_connected = False
            return False, 0
        finally:
            conn.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            success, count = self.sync_once()
            if not success:
                # Exponential backoff capped at 120s
                self.backoff_delay = min(120.0, self.backoff_delay * 1.5)
                self._stop_event.wait(self.backoff_delay)
            else:
                self.backoff_delay = self.sync_interval
                self._stop_event.wait(self.sync_interval)
