# cache_routes.py
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
import hashlib
from typing import Optional

from app.core.utils import (
    cleanup_old_cache_files,
    generate_cache_key
)
from app.core.config import settings

router = APIRouter()

@router.post("/cleanup")
async def cleanup_cache(max_age_hours: int = Query(24, description="삭제할 파일의 최대 나이(시간)")):
    """24시간 이상 지난 캐시 파일 정리"""
    try:
        cleanup_old_cache_files(max_age_hours)
        return {"status": "success", "message": f"{max_age_hours}시간 이상된 캐시 파일을 정리했습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"캐시 정리 실패: {str(e)}")


@router.get("/stats")
async def cache_stats():
    """캐시 통계 정보"""
    try:
        cache_dir = Path(settings.CACHE_DIR)
        converted_dir = Path(settings.CONVERTED_DIR)
        
        cache_files = list(cache_dir.glob("*"))
        converted_files = list(converted_dir.glob("*.pdf"))

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


@router.post("/clear-all")
async def clear_all_cache(confirm: bool = Query(False, description="확인 여부")):
    """모든 캐시 파일 삭제 (위험한 작업)"""
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="위험한 작업입니다. confirm=true 파라미터를 추가하세요"
        )
    
    try:
        cache_dir = Path(settings.CACHE_DIR)
        converted_dir = Path(settings.CONVERTED_DIR)
        
        # 캐시 디렉토리의 모든 파일 삭제
        cache_deleted = 0
        if cache_dir.exists():
            for file_path in cache_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    cache_deleted += 1
        
        # 변환된 파일 디렉토리의 모든 파일 삭제
        converted_deleted = 0
        if converted_dir.exists():
            for file_path in converted_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    converted_deleted += 1
        
        # Redis 캐시도 정리 (선택사항 - 필요시 구현)
        # TODO: Redis 연결하여 aview:file:* 패턴 키들 삭제
        
        return {
            "status": "success",
            "message": f"모든 캐시 파일이 삭제되었습니다",
            "deleted": {
                "cache_files": cache_deleted,
                "converted_files": converted_deleted,
                "total": cache_deleted + converted_deleted
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전체 캐시 삭제 실패: {str(e)}")


@router.delete("/file")
async def delete_file_cache(
    url: Optional[str] = Query(None, description="삭제할 파일의 URL"), 
    path: Optional[str] = Query(None, description="삭제할 파일의 로컬 경로")
):
    """특정 파일의 캐시 삭제"""
    if not url and not path:
        raise HTTPException(
            status_code=400, 
            detail="url 또는 path 중 하나는 필수입니다"
        )
    
    if url and path:
        raise HTTPException(
            status_code=400, 
            detail="url과 path 중 하나만 제공해야 합니다"
        )
    
    try:
        cache_dir = Path(settings.CACHE_DIR)
        converted_dir = Path(settings.CONVERTED_DIR)
        
        # 캐시 키 생성
        source = url if url else str(Path(path).resolve())
        cache_key = generate_cache_key(source)
        file_hash = hashlib.md5(source.encode()).hexdigest()
        
        deleted_files = []
        
        # 원본 캐시 파일들 찾아서 삭제
        for cache_file in cache_dir.glob(f"{file_hash}.*"):
            if cache_file.is_file():
                cache_file.unlink()
                deleted_files.append(str(cache_file))
        
        # 변환된 파일들 찾아서 삭제 (stem으로 찾기)
        for converted_file in converted_dir.glob(f"{file_hash}.*"):
            if converted_file.is_file():
                converted_file.unlink()
                deleted_files.append(str(converted_file))
        
        # TODO: Redis에서 해당 캐시 키 삭제
        # redis_client.delete(cache_key)
        
        if not deleted_files:
            return {
                "status": "info",
                "message": "삭제할 캐시 파일이 없습니다",
                "source": source,
                "cache_key": cache_key
            }
        
        return {
            "status": "success",
            "message": f"{len(deleted_files)}개의 캐시 파일이 삭제되었습니다",
            "source": source,
            "deleted_files": deleted_files
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 캐시 삭제 실패: {str(e)}")
