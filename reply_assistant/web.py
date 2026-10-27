from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .bootstrap import build_service
from .config import Settings, load_settings
from .demo_data import seed_demo
from .models import InboundReply
from .service import DraftGateError, ReplyService
from .storage import CardNotFound, InvalidTransition


STATIC_DIR = Path(__file__).resolve().parent / "static"


class DraftEdit(BaseModel):
    draft: str = Field(min_length=1, max_length=4000)


class InboundPayload(BaseModel):
    message_id: str
    thread_id: str
    from_name: str
    from_email: str
    company: str = ""
    subject: str = ""
    body: str
    received_at: str


def create_app(settings: Settings | None = None, service: ReplyService | None = None) -> FastAPI:
    settings = settings or load_settings()
    service = service or build_service(settings)
    app = FastAPI(title="Cold Email Reply Assistant", version="1.0.0")

    def authorize(request: Request) -> None:
        if settings.demo:
            return
        supplied = request.headers.get("X-App-Token", "")
        if not settings.access_token or not hmac.compare_digest(supplied, settings.access_token):
            raise HTTPException(status_code=401, detail="invalid app token")

    @app.exception_handler(CardNotFound)
    async def not_found(_request: Request, _exc: CardNotFound):
        return _json_error(404, "card not found")

    @app.exception_handler(InvalidTransition)
    async def transition_error(_request: Request, exc: InvalidTransition):
        return _json_error(409, str(exc))

    @app.exception_handler(DraftGateError)
    async def gate_error(_request: Request, exc: DraftGateError):
        return _json_error(422, "draft rejected", [item.label() for item in exc.violations])

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/cards")
    def cards(request: Request):
        authorize(request)
        return {"mode": settings.mode, "cards": [card.to_dict() for card in service.store.list()]}

    @app.post("/api/inbound", status_code=201)
    def inbound(payload: InboundPayload, request: Request):
        authorize(request)
        return service.process(InboundReply(**payload.dict())).to_dict()

    @app.post("/api/cards/{card_id}/edit")
    def edit(card_id: str, payload: DraftEdit, request: Request):
        authorize(request)
        return service.edit(card_id, payload.draft).to_dict()

    @app.post("/api/cards/{card_id}/approve")
    def approve(card_id: str, request: Request):
        authorize(request)
        try:
            result = service.approve(card_id)
        except (DraftGateError, InvalidTransition, CardNotFound):
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"provider result uncertain; verify before retrying ({type(exc).__name__})",
            ) from exc
        return {"sent_now": result.sent_now, "card": result.card.to_dict()}

    @app.post("/api/cards/{card_id}/skip")
    def skip(card_id: str, request: Request):
        authorize(request)
        return service.skip(card_id).to_dict()

    @app.post("/api/demo/reset")
    def reset(request: Request):
        authorize(request)
        if not settings.demo:
            raise HTTPException(status_code=404, detail="not available")
        service.store.clear()
        cards = seed_demo(service)
        return {"cards": [card.to_dict() for card in cards]}

    return app


def _json_error(status_code: int, error: str, violations: list[str] | None = None):
    from fastapi.responses import JSONResponse

    payload: dict[str, object] = {"error": error}
    if violations is not None:
        payload["violations"] = violations
    return JSONResponse(payload, status_code=status_code)


app = create_app()
