"""Template rendering with language and account in context."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.i18n import LANG_NAMES, pick_lang, translate

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

LANG_COOKIE = "sc_lang"


def request_lang(request: Request) -> str:
    q = request.query_params.get("lang")
    if q:
        return pick_lang(q, settings.default_lang)
    return pick_lang(request.cookies.get(LANG_COOKIE), settings.default_lang)


def render(request: Request, name: str, **ctx):
    lang = request_lang(request)
    status_code = ctx.pop("status_code", 200)
    account = getattr(request.state, "account", None)
    context = {
        "request": request,
        "lang": lang,
        "lang_names": LANG_NAMES,
        "languages": settings.language_list,
        "t": lambda key: translate(lang, key),
        "account": account,
        "settings": settings,
        "app_env": settings.env,
    }
    context.update(ctx)
    response = templates.TemplateResponse(request, name, context, status_code=status_code)
    if request.query_params.get("lang"):
        response.set_cookie(LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response
