

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.utils import check_libreoffice
from app.utils import get_redis, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지 - 서비스 상태 및 테스트 UI"""
    templates = get_templates(request)
    libre_status = check_libreoffice()

    # Redis 연결 상태 확인
    redis_client = get_redis(request)
    try:
        redis_status = bool(redis_client.ping()) if redis_client else False
    except Exception:
        redis_status = False

    context = {
        "request": request,
        "title": "A-View Document Processor",
        "libre_status": libre_status,
        "redis_status": redis_status,
    }
    return templates.TemplateResponse("index.html", context)


@router.get("/usage", response_class=HTMLResponse)
async def usage(request: Request):
    """사용법 페이지"""
    templates = get_templates(request)
    context = {
        "request": request,
        "title": "사용법",
    }
    return templates.TemplateResponse("usage.html", context)
