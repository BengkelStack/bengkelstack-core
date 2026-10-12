import json
import sqlite3
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os
from typing import Tuple, Any, Optional

from database.db import get_connection, run_migrations
from app.repositories import (
    list_motor_models,
    list_parts,
    list_services,
    get_workshop_settings,
    update_workshop_settings,
)
from app.pricing_engine import calculate_cart_pricing
from app.work_order_service import (
    find_vehicle_by_plate,
    create_work_order,
    get_work_order,
    quick_update_master_price,
    get_service_history_by_plate,
    get_model_pricing_reference,
    format_thermal_receipt,
)
from app.security import (
    verify_auth,
    RateLimiter,
    get_security_headers,
    MAX_PAYLOAD_SIZE,
)
from app.invoice_vision import parse_invoice_text, parse_invoice_json
from app.catalog_matcher import reconcile_invoice_document
from app.cloud_service import (
    register_tenant,
    login_user,
    logout_user,
    get_authenticated_user,
    list_tenants,
    update_tenant_status,
    generate_tenant_sync_key,
    list_tenant_sync_keys,
    get_fleet_metrics,
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

# Institutional Global Rate Limiter: 120 req/min per IP
rate_limiter = RateLimiter(max_requests=120, window_seconds=60.0)


def get_bearer_token(headers: Optional[dict]) -> Optional[str]:
    if not headers:
        return None
    for k, v in headers.items():
        if k.lower() == "authorization":
            val = str(v).strip()
            if val.startswith("Bearer ") or val.startswith("bearer "):
                return val[7:].strip()
    return None


def handle_api_request(
    conn: sqlite3.Connection,
    method: str,
    path: str,
    body: Optional[dict] = None,
    headers: Optional[dict] = None
) -> Tuple[int, Any]:
    parsed = urllib.parse.urlparse(path)
    endpoint = parsed.path
    query_params = urllib.parse.parse_qs(parsed.query)

    # ponytail: clean routing with standard library urllib
    if method == "GET":
        if endpoint == "/api/motor-models":
            search = query_params.get("search", [None])[0]
            return 200, list_motor_models(conn, search)

        elif endpoint == "/api/parts":
            search = query_params.get("search", [None])[0]
            return 200, list_parts(conn, search)

        elif endpoint == "/api/services":
            search = query_params.get("search", [None])[0]
            return 200, list_services(conn, search)

        elif endpoint == "/api/settings":
            return 200, get_workshop_settings(conn)

        elif endpoint == "/api/vehicle-lookup":
            plate = query_params.get("plate", [None])[0]
            if not plate:
                return 400, {"error": "Missing plate query parameter"}
            vehicle = find_vehicle_by_plate(conn, plate)
            return 200, vehicle

        elif endpoint == "/api/history/plate":
            plate = query_params.get("plate", [None])[0]
            if not plate:
                return 400, {"error": "Missing plate query parameter"}
            history = get_service_history_by_plate(conn, plate)
            return 200, history

        elif endpoint == "/api/reference/model":
            model_id_str = query_params.get("motor_model_id", [None])[0]
            if not model_id_str:
                return 400, {"error": "Missing motor_model_id query parameter"}
            try:
                ref = get_model_pricing_reference(conn, int(model_id_str))
                return 200, ref
            except ValueError:
                return 400, {"error": "Invalid motor_model_id"}

        elif endpoint.startswith("/api/work-orders/"):
            parts = endpoint.strip("/").split("/")
            if len(parts) >= 3:
                try:
                    wo_id = int(parts[2])
                    wo = get_work_order(conn, wo_id)
                    if not wo:
                        return 404, {"error": "Work order not found"}
                    if len(parts) == 4 and parts[3] == "receipt":
                        return 200, {
                            "work_order_id": wo_id,
                            "receipt_text": format_thermal_receipt(wo, conn=conn)
                        }
                    elif len(parts) == 3:
                        return 200, wo
                    else:
                        return 404, {"error": "Unknown sub-resource"}
                except ValueError:
                    return 400, {"error": "Invalid work order id"}

        # Tier 2 Cloud Platform Endpoints
        elif endpoint == "/api/v1/owner/profile":
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] not in ("OWNER", "SUPERADMIN"):
                return 401, {"error": "Unauthorized: valid session token required"}
            return 200, {
                "status": "success",
                "data": {
                    "user": {
                        "id": user["user_id"],
                        "email": user["email"],
                        "full_name": user["full_name"],
                        "role": user["role"]
                    },
                    "tenant": {
                        "id": user["tenant_id"],
                        "name": user["tenant_name"],
                        "slug": user["tenant_slug"],
                        "plan": user["tenant_plan"],
                        "status": user["tenant_status"]
                    } if user["tenant_id"] else None
                }
            }

        elif endpoint == "/api/v1/owner/sync-keys":
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] not in ("OWNER", "SUPERADMIN"):
                return 401, {"error": "Unauthorized: valid session token required"}
            if not user["tenant_id"]:
                return 400, {"error": "No associated tenant"}
            keys = list_tenant_sync_keys(conn, user["tenant_id"])
            return 200, {"status": "success", "data": keys}

        elif endpoint == "/api/v1/admin/tenants":
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] != "SUPERADMIN":
                return 401 if not user else 403, {"error": "Forbidden: SuperAdmin role required"}
            page = int(query_params.get("page", [1])[0])
            limit = int(query_params.get("limit", [20])[0])
            status_f = query_params.get("status", [None])[0]
            search = query_params.get("search", [None])[0]
            res = list_tenants(conn, page=page, limit=limit, status_filter=status_f, search=search)
            return 200, {"status": "success", "data": res}

        elif endpoint == "/api/v1/admin/metrics/overview":
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] != "SUPERADMIN":
                return 401 if not user else 403, {"error": "Forbidden: SuperAdmin role required"}
            metrics = get_fleet_metrics(conn)
            return 200, {"status": "success", "data": metrics}

    elif method == "POST":
        if endpoint == "/api/calculate":
            if not body or "items" not in body:
                return 400, {"error": "Missing items in payload"}
            motor_model_id = body.get("motor_model_id")
            items = body.get("items", [])
            cart = calculate_cart_pricing(conn, items, motor_model_id=motor_model_id)
            return 200, cart

        elif endpoint == "/api/work-orders":
            if not body:
                return 400, {"error": "Missing payload"}
            try:
                order = create_work_order(
                    conn,
                    plate_number=body["plate_number"],
                    motor_model_id=int(body["motor_model_id"]),
                    customer_name=body["customer_name"],
                    items=body["items"],
                    status=body.get("status", "COMPLETED"),
                    payment_method=body.get("payment_method", "CASH"),
                    cash_received=float(body["cash_received"]) if body.get("cash_received") is not None else None,
                    idempotency_key=body.get("idempotency_key")
                )
                return 201, order
            except (KeyError, ValueError) as e:
                return 400, {"error": str(e)}

        elif endpoint == "/api/settings":
            if not body:
                return 400, {"error": "Missing payload"}
            try:
                res = update_workshop_settings(
                    conn,
                    workshop_name=body.get("workshop_name"),
                    currency_symbol=body.get("currency_symbol"),
                    currency_code=body.get("currency_code"),
                    receipt_header=body.get("receipt_header"),
                    receipt_footer=body.get("receipt_footer"),
                    min_margin_pct=float(body["min_margin_pct"]) if body.get("min_margin_pct") is not None else None
                )
                return 200, res
            except (KeyError, ValueError) as e:
                return 400, {"error": str(e)}

        elif endpoint == "/api/master/quick-update":
            if not body:
                return 400, {"error": "Missing payload"}
            try:
                res = quick_update_master_price(
                    conn,
                    item_type=body["item_type"],
                    item_id=int(body["item_id"]),
                    new_price=float(body["new_price"]) if body.get("new_price") is not None else None,
                    new_install_fee=float(body["new_install_fee"]) if body.get("new_install_fee") is not None else None,
                    motor_model_id=int(body["motor_model_id"]) if body.get("motor_model_id") is not None else None,
                    save_as_model_custom=bool(body.get("save_as_model_custom", False))
                )
                return 200, res
            except (KeyError, ValueError) as e:
                return 400, {"error": str(e)}

        elif endpoint == "/api/invoices/scan":
            if not body or ("raw_text" not in body and "invoice" not in body):
                return 400, {"error": "Missing raw_text or invoice in payload"}

            apply_update = bool(body.get("apply_update", False))
            min_margin = float(body.get("min_margin_pct", 25.0))

            if "raw_text" in body and body["raw_text"]:
                doc = parse_invoice_text(body["raw_text"])
            elif "invoice" in body and isinstance(body["invoice"], dict):
                doc = parse_invoice_json(body["invoice"])
            else:
                return 400, {"error": "Invalid invoice payload format"}

            matches = reconcile_invoice_document(conn, doc, apply_update=apply_update, min_margin_pct=min_margin)

            matched_count = sum(1 for m in matches if m.part_id is not None)
            violations_count = sum(1 for m in matches if m.markup_violation)

            return 200, {
                "invoice": doc.to_dict(),
                "reconciliation": [m.to_dict() for m in matches],
                "financial_audit": {
                    "is_financially_reconciled": doc.is_financially_reconciled,
                    "reconciliation_delta": doc.reconciliation_delta,
                    "items_count": len(doc.items),
                    "matched_count": matched_count,
                    "unmatched_count": len(doc.items) - matched_count,
                    "margin_violations_count": violations_count,
                }
            }

        # Tier 2 Cloud Platform Endpoints
        elif endpoint == "/api/v1/auth/register":
            if not body:
                return 400, {"error": "Missing payload"}
            ok, code, res = register_tenant(
                conn,
                tenant_name=body.get("tenant_name", ""),
                owner_name=body.get("owner_name", "Owner"),
                email=body.get("email", ""),
                password=body.get("password", ""),
                country_code=body.get("country_code", "ID"),
                currency=body.get("currency", "IDR"),
                plan=body.get("plan", "FREE"),
                slug=body.get("slug")
            )
            return code, res

        elif endpoint == "/api/v1/auth/login":
            if not body:
                return 400, {"error": "Missing payload"}
            ok, code, res = login_user(
                conn,
                email=body.get("email", ""),
                password=body.get("password", "")
            )
            return code, res

        elif endpoint == "/api/v1/auth/logout":
            token = get_bearer_token(headers)
            if not token:
                return 401, {"error": "Missing bearer token"}
            logout_user(conn, token)
            return 200, {"status": "success", "message": "Logged out successfully"}

        elif endpoint == "/api/v1/owner/sync-key/generate":
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] not in ("OWNER", "SUPERADMIN"):
                return 401, {"error": "Unauthorized: valid session token required"}
            if not user["tenant_id"]:
                return 400, {"error": "No associated tenant"}
            label = body.get("label", "Edge Terminal") if body else "Edge Terminal"
            ok, code, res = generate_tenant_sync_key(conn, user["tenant_id"], label=label)
            return code, res

    elif method == "PATCH":
        if endpoint.startswith("/api/v1/admin/tenants/") and endpoint.endswith("/status"):
            token = get_bearer_token(headers)
            user = get_authenticated_user(conn, token)
            if not user or user["role"] != "SUPERADMIN":
                return 401 if not user else 403, {"error": "Forbidden: SuperAdmin role required"}
            parts = endpoint.strip("/").split("/")
            if len(parts) == 6 and parts[3] == "tenants" and parts[5] == "status":
                try:
                    tenant_id = int(parts[4])
                    if not body or "status" not in body:
                        return 400, {"error": "Missing status in payload"}
                    ok, code, res = update_tenant_status(
                        conn, tenant_id, new_status=body["status"], reason=body.get("reason")
                    )
                    return code, res
                except ValueError:
                    return 400, {"error": "Invalid tenant id"}

    return 404, {"error": f"Endpoint not found: {method} {endpoint}"}


class WorkshopRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        for h_name, h_val in get_security_headers().items():
            self.send_header(h_name, h_val)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        if not rate_limiter.is_allowed(client_ip):
            self._send_json(429, {"error": "Too Many Requests", "retry_after": 60})
            return

        if self.path.startswith("/api/"):
            auth_ok, code, msg = verify_auth(dict(self.headers), client_ip)
            if not auth_ok:
                self._send_json(code, {"error": msg})
                return

            try:
                conn = get_connection()
                status, data = handle_api_request(conn, "GET", self.path, None, headers=dict(self.headers))
                conn.close()
            except Exception:
                status, data = 500, {"error": "Internal server error"}

            self._send_json(status, data)
        else:
            self._serve_static()

    def do_POST(self):
        self._handle_mutation("POST")

    def do_PATCH(self):
        self._handle_mutation("PATCH")

    def _handle_mutation(self, method: str):
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        if not rate_limiter.is_allowed(client_ip):
            self._send_json(429, {"error": "Too Many Requests", "retry_after": 60})
            return

        if self.path.startswith("/api/"):
            auth_ok, code, msg = verify_auth(dict(self.headers), client_ip)
            if not auth_ok:
                self._send_json(code, {"error": msg})
                return

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_PAYLOAD_SIZE:
                self._send_json(413, {"error": "Payload Too Large: exceeds 1MB limit"})
                return

            body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                body = {}

            try:
                conn = get_connection()
                status, data = handle_api_request(conn, method, self.path, body, headers=dict(self.headers))
                conn.close()
            except Exception:
                status, data = 500, {"error": "Internal server error"}

            self._send_json(status, data)
        else:
            self.send_error(404)

    def _send_json(self, status: int, data: Any):
        body_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for h_name, h_val in get_security_headers().items():
            self.send_header(h_name, h_val)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body_bytes)

    def _serve_static(self):
        req_path = self.path.split("?")[0]
        if req_path == "/" or req_path == "":
            file_name = "index.html"
        else:
            file_name = urllib.parse.unquote(req_path.lstrip("/"))

        base_dir = os.path.abspath(STATIC_DIR)
        file_path = os.path.abspath(os.path.join(base_dir, file_name))
        
        # Ensure path strictly stays within STATIC_DIR
        try:
            if os.path.commonpath([base_dir, file_path]) != base_dir:
                self.send_error(403, "Access denied")
                return
        except ValueError:
            self.send_error(403, "Access denied")
            return

        if not os.path.isfile(file_path):
            self.send_error(404, "File not found")
            return

        content_type = "text/html"
        if file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".js"):
            content_type = "application/javascript"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        for h_name, h_val in get_security_headers().items():
            self.send_header(h_name, h_val)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Silence console log noise
        pass


def run_server(port: int = 8089):
    run_migrations()
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, WorkshopRequestHandler)
    print(f"Workshop POS & Pricing Engine running on http://127.0.0.1:{port} (Threading mode)")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
