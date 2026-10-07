import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .config import Settings, get_settings
from .proxmox import ProxmoxClient, ProxmoxError
from .security import verify_router_key
from .wol import send_wol

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ollama-router")

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logger.setLevel(settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.start_lock = asyncio.Lock()
        app.state.upstream = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.upstream_connect_timeout,
                read=None,
                write=settings.upstream_write_timeout,
                pool=settings.upstream_pool_timeout,
            ),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        app.state.proxmox = ProxmoxClient(settings)
        yield
        await app.state.upstream.aclose()
        await app.state.proxmox.close()

    app = FastAPI(title="Ollama Proxmox Router", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def authentication(request: Request, call_next):
        try:
            verify_router_key(request, settings)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        return await call_next(request)

    async def upstream_ready(client: httpx.AsyncClient) -> bool:
        try:
            response = await client.get(
                f"{settings.upstream_base_url}{settings.upstream_health_path}",
                timeout=settings.upstream_connect_timeout,
            )
            return 200 <= response.status_code < 300
        except httpx.HTTPError:
            return False

    async def ensure_upstream_ready(request: Request) -> None:
        client = request.app.state.upstream
        if await upstream_ready(client):
            return
        async with request.app.state.start_lock:
            if await upstream_ready(client):
                return
            try:
                started = await request.app.state.proxmox.ensure_started()
                logger.info("VM/CT Ollama %s", "avviato" if started else "gia in esecuzione")
            except ProxmoxError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            loop = asyncio.get_running_loop()
            deadline = loop.time() + settings.startup_timeout
            delay = settings.startup_poll_initial
            while loop.time() < deadline:
                if await request.is_disconnected():
                    raise HTTPException(status_code=499, detail="Client disconnesso durante il cold start")
                if await upstream_ready(client):
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, settings.startup_poll_max)
        raise HTTPException(
            status_code=503,
            detail="Ollama non e diventato pronto entro il timeout",
            headers={"Retry-After": "10"},
        )

    @app.get("/")
    async def root():
        return {"service": "ollama-proxmox-router", "docs": "/docs"}

    @app.get("/health/live")
    async def live():
        return {"router": "ok"}

    @app.get("/health/ready")
    async def ready(request: Request):
        is_ready = await upstream_ready(request.app.state.upstream)
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"router": "ok", "upstream": "ready" if is_ready else "offline"},
        )

    @app.post("/gaming/start")
    async def gaming_start():
        if not settings.gaming_mac:
            raise HTTPException(status_code=501, detail="GAMING_MAC non configurato")
        try:
            await asyncio.to_thread(send_wol, settings.gaming_mac, settings.gaming_broadcast, settings.gaming_wol_port)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content={"status": "accepted", "message": "Wake-on-LAN inviato"})

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy(path: str, request: Request):
        if path.startswith("health/") or path == "gaming/start":
            raise HTTPException(status_code=404)
        await ensure_upstream_ready(request)
        client: httpx.AsyncClient = request.app.state.upstream
        target = f"{settings.upstream_base_url}/" + quote(path, safe="/@:+")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
        if settings.upstream_authorization:
            headers["authorization"] = settings.upstream_authorization
        else:
            headers.pop("authorization", None)
        body = await request.body()
        upstream_request = client.build_request(
            request.method, target, params=request.query_params, headers=headers, content=body
        )
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Connessione upstream fallita: {exc}") from exc
        response_headers = {
            k: v for k, v in upstream.headers.items()
            if k.lower() not in HOP_BY_HOP and k.lower() != "content-encoding"
        }
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=response_headers,
            background=BackgroundTask(upstream.aclose),
        )

    return app


app = create_app()
