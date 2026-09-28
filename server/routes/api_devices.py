from fastapi import APIRouter, Depends
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from ptr_resolver import resolve_ptr_async

router = APIRouter(prefix="/api/devices", tags=["devices"], dependencies=[Depends(get_current_user)])

class UpdateDeviceRequest(BaseModel):
    client_ip: str
    friendly_name: str
    icon: str = "device"
    group_name: str = "default"

@router.get("")
def list_devices():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Lightly discover any recent unindexed client IPs without full historical table scans
        cursor.execute("""
        INSERT OR IGNORE INTO devices (client_ip, hostname, friendly_name, icon, total_queries, blocked_queries, first_seen, last_seen)
        SELECT 
            l.client_ip,
            l.client_ip,
            NULL,
            'desktop',
            COUNT(*),
            SUM(CASE WHEN l.response_type = 'BLOCKED' THEN 1 ELSE 0 END),
            MIN(l.request_ts),
            MAX(l.request_ts)
        FROM (SELECT * FROM log_entries ORDER BY id DESC LIMIT 500) l
        LEFT JOIN devices d ON l.client_ip = d.client_ip
        WHERE d.client_ip IS NULL AND l.client_ip IS NOT NULL AND TRIM(l.client_ip) != ''
        GROUP BY l.client_ip;
        """)
        conn.commit()

        cursor.execute("SELECT * FROM devices ORDER BY total_queries DESC;")
        devices = [dict(r) for r in cursor.fetchall()]
        return devices
    finally:
        conn.close()

@router.post("/update")
def update_device(req: UpdateDeviceRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE devices 
        SET friendly_name = ?, icon = ?, group_name = ?
        WHERE client_ip = ?;
        """, (req.friendly_name.strip(), req.icon, req.group_name, req.client_ip.strip()))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@router.post("/resolve-ptr/{client_ip}")
def trigger_ptr(client_ip: str):
    resolve_ptr_async(client_ip.strip(), force=True)
    return {"success": True, "message": "PTR lookup dispatched"}

@router.delete("/{client_ip}")
def delete_device(client_ip: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE client_ip = ?;", (client_ip.strip(),))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@router.post("/clear-demo")
def clear_demo_data():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Specifically target only the seeded demo client IPs to avoid wiping real user LAN devices on 192.168.1.x
        demo_ips = ("192.168.1.45", "192.168.1.12", "192.168.1.15", "192.168.1.22", "192.168.1.99", "192.168.1.10")
        placeholders = ",".join("?" for _ in demo_ips)
        cursor.execute(f"DELETE FROM devices WHERE client_ip IN ({placeholders});", demo_ips)
        cursor.execute(f"DELETE FROM log_entries WHERE client_ip IN ({placeholders});", demo_ips)
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('demo_data_cleared', 'true');")
        conn.commit()
        return {"success": True, "message": "Demo devices and logs cleared permanently"}
    finally:
        conn.close()


