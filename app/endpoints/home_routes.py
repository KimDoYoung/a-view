

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.utils import check_libreoffice


router = APIRouter()


def _get_redis(request: Request):
    # main.py에서 app.state.redis에 넣어둔 인스턴스를 꺼내씀
    return getattr(request.app.state, "redis", None)


def _get_templates(request: Request):
    # main.py에서 app.state.templates에 넣어둔 인스턴스를 꺼내씀
    return request.app.state.templates

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지 - 서비스 상태 및 테스트 UI"""
    templates = _get_templates(request)
    libre_status = check_libreoffice()

    # Redis 연결 상태 확인
    redis_client = _get_redis(request)
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