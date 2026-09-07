import os
import sys
import threading
import http.server
import socketserver
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure server directory is in sys.path and permissions are open
try:
    os.umask(0)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "routes"))

from database import init_db
from seed_data import seed_initial_data
from tls_manager import ensure_tls_certificates
from retention import start_retention_scheduler
from benchmark import start_benchmark_scheduler
from auth import is_setup_completed, decode_access_token

# Import routers
from api_auth import router as auth_router
from api_stats import router as stats_router
from api_logs import router as logs_router
from api_blocklists import router as blocklists_router
from api_rules import router as rules_router
from api_devices import router as devices_router
from api_local_dns import router as local_dns_router
from api_routing import router as routing_router
from api_upstreams import router as upstreams_router
from api_tools import router as tools_router
from api_control import router as control_router
from api_backup import router as backup_router
from api_services import router as services_router

PUBLIC_DIR = BASE_DIR.parent / "public"
HTTP_PORT = int(os.getenv("HTTP_PORT", "3000"))
HTTPS_PORT = int(os.getenv("HTTPS_PORT", "3443"))
ENABLE_HTTPS = os.getenv("ENABLE_HTTPS", "true").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[Server] Initializing BlockyDNS Hub database & schema...")
    init_db()
    seed_initial_data()
    start_retention_scheduler()
    start_benchmark_scheduler()
    yield
    # Shutdown
    print("[Server] Shutting down BlockyDNS Hub...")

app = FastAPI(title="BlockyDNS Hub", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hardened Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

# Include all API routers
app.include_router(auth_router)
app.include_router(stats_router)
app.include_router(logs_router)
app.include_router(blocklists_router)
app.include_router(rules_router)
app.include_router(devices_router)
app.include_router(local_dns_router)
app.include_router(routing_router)
app.include_router(upstreams_router)
app.include_router(tools_router)
app.include_router(control_router)
app.include_router(backup_router)
app.include_router(services_router)

# Mount static frontend assets
app.mount("/css", StaticFiles(directory=str(PUBLIC_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(PUBLIC_DIR / "js")), name="js")
if (PUBLIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(PUBLIC_DIR / "assets")), name="assets")

@app.get("/login")
def login_page(request: Request):
    token = request.cookies.get("blockydns_token")
    if token and decode_access_token(token) and is_setup_completed():
        return RedirectResponse(url="/")
    return FileResponse(str(PUBLIC_DIR / "login.html"))

@app.get("/")
def index_page(request: Request):
    if not is_setup_completed():
        return RedirectResponse(url="/login")
    token = request.cookies.get("blockydns_token")
    if not token or not decode_access_token(token):
        resp = RedirectResponse(url="/login")
        if token:
            resp.delete_cookie("blockydns_token", path="/")
        return resp
    return FileResponse(str(PUBLIC_DIR / "index.html"))

# Background HTTP to HTTPS Redirector
def start_http_redirect_server():
    class RedirectHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "localhost").split(":")[0]
            target_url = f"https://{host}:{HTTPS_PORT}{self.path}"
            self.send_response(301)
            self.send_header("Location", target_url)
            self.end_headers()

    try:
        with socketserver.TCPServer(("", HTTP_PORT), RedirectHandler) as httpd:
            print(f"[Redirect] HTTP server listening on port {HTTP_PORT} -> Redirecting to HTTPS {HTTPS_PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[Redirect] Note: HTTP redirect server on port {HTTP_PORT} could not start: {e}")

if __name__ == "__main__":
    cert_file, key_file = ensure_tls_certificates()

    # Start HTTP redirect in daemon thread
    redirect_thread = threading.Thread(target=start_http_redirect_server, daemon=True)
    redirect_thread.start()

    print(f"\n=======================================================")
    print(f"[SECURE] BlockyDNS Hub Starting with End-to-End HTTPS Encryption")
    print(f"   HTTPS URL:  https://localhost:{HTTPS_PORT}")
    print(f"   HTTP URL:   http://localhost:{HTTP_PORT} (Redirects to HTTPS)")
    print(f"   Certificate: {cert_file}")
    print(f"=======================================================\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=HTTPS_PORT,
        ssl_certfile=cert_file if ENABLE_HTTPS else None,
        ssl_keyfile=key_file if ENABLE_HTTPS else None,
        log_level="info"
    )
