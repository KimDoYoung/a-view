# aview_routes.py
from fastapi import APIRouter, Request, HTTPException, Query

from utils import (
    cleanup_old_cache_files,
    CACHE_DIR,
    CONVERTED_DIR,
)

router = APIRouter()


def _get_redis(request: Request):
    # main.py에서 app.state.redis에 넣어둔 인스턴스를 꺼내씀
    return getattr(request.app.state, "redis", None)


def _get_templates(request: Request):
    # main.py에서 app.state.templates에 넣어둔 인스턴스를 꺼내씀
    return request.app.state.templates


@router.post("/api/cache/cleanup")
async def cleanup_cache(max_age_hours: int = Query(24, description="삭제할 파일의 최대 나이(시간)")):
    """캐시 파일 정리"""
    try:
        cleanup_old_cache_files(max_age_hours)
        return {"status": "success", "message": f"{max_age_hours}시간 이상된 캐시 파일을 정리했습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"캐시 정리 실패: {str(e)}")


@router.get("/api/cache/stats")
async def cache_stats():
    """캐시 통계 정보"""
    try:
        cache_files = list(CACHE_DIR.glob("*"))
        converted_files = list(CONVERTED_DIR.glob("*.pdf"))

        cache_size = sum(f.stat().st_size for f in cache_files if f.is_file())
        converted_size = sum(f.stat().st_size for f in converted_files if f.is_file())

        return {
            "cache": {
                "files": len([f for f in cache_files if f.is_file()]),
                "size_mb": round(cache_size / (1024 * 1024), 2),
            },
            "converted": {
                "files": len(converted_files),
                "size_mb": round(converted_size / (1024 * 1024), 2),
            },
            "total_size_mb": round((cache_size + converted_size) / (1024 * 1024), 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")
