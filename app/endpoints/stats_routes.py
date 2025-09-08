# stats_routes.py
"""
모듈 설명: 
    - 통계관련 엔드포인트 모음
주요 기능:
    - get /system-status : 시스템 상태 조회
    - get /dashboard : 통계 대시보드 데이터 조회
    - get /daily/{date} : 특정 날짜 통계 조회
    - get /export : 통계 데이터 내보내기 (json/csv)

작성자: 김도영
작성일: 2025-09-08
버전: 1.0
"""
from fastapi import APIRouter, Query, Request
from datetime import date
from pathlib import Path
from core.utils import check_libreoffice
from core.config import settings

router = APIRouter()

@router.get("/system-status")
async def get_system_status(request: Request):
    """시스템 상태 조회"""
    try:
        # Redis 상태 확인
        redis_client = request.app.state.redis
        redis_status = False
        redis_memory = 0
        
        try:
            redis_client.ping()
            redis_status = True
            # Redis 메모리 사용량 (대략적)
            info = redis_client.info('memory')
            redis_memory = round(info.get('used_memory', 0) / 1024 / 1024, 2)
        except Exception:
            pass
        
        # LibreOffice 상태
        libre_status, libre_version = check_libreoffice()
        
        # 캐시 디렉토리 상태
        cache_dir = Path(settings.CACHE_DIR)
        cache_files = 0
        cache_size = 0
        
        if cache_dir.exists():
            cache_files = len(list(cache_dir.rglob('*'))) - len(list(cache_dir.rglob('*/')))  # 폴더 제외
            cache_size = round(sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file()) / 1024 / 1024, 2)
        
        # DB 크기
        db_path = Path(settings.STATS_DB_PATH)
        db_size = round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0
        
        return {
            "redis": redis_status,
            "redisMemory": redis_memory,
            "libreOffice": libre_status,
            "libreVersion": libre_version,
            "cacheFiles": cache_files,
            "cacheSize": cache_size,
            "dbSize": db_size,
            "timestamp": date.today().isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "redis": False,
            "libreOffice": False,
            "cacheFiles": 0,
            "cacheSize": 0,
            "dbSize": 0
        }

@router.get("/dashboard")
async def stats_dashboard(request: Request, days: int = Query(7, ge=1, le=365)):
    """통계 대시보드 데이터"""
    db = request.app.state.stats_db
    
    try:
        # 파일 타입별 통계
        file_types = db.get_file_type_stats(days)
        
        # TOP 파일들
        top_files = db.get_top_files(days, limit=10)
        
        # 시간대별 분포
        hourly_distribution = db.get_hourly_distribution(days)
        
        # 캐시 효율성
        cache_effectiveness = db.get_cache_effectiveness(days)
        
        # 에러 통계
        errors = db.get_error_stats(days)
        
        # 출력 형식별 통계 (PDF vs HTML)
        output_formats = {}
        for file_type, data in file_types.items():
            # 간단한 추정: docx, pptx -> PDF가 많고, txt -> HTML이 많다고 가정
            if file_type in ['docx', 'pptx', 'xlsx']:
                output_formats['pdf'] = output_formats.get('pdf', 0) + data['count']
            else:
                output_formats['html'] = output_formats.get('html', 0) + data['count']
        
        return {
            "period": days,
            "file_types": file_types,
            "top_files": top_files,
            "hourly_distribution": hourly_distribution,
            "cache_effectiveness": cache_effectiveness,
            "errors": errors,
            "output_formats": output_formats,
            "summary": {
                "total_conversions": cache_effectiveness.get('total_requests', 0),
                "cache_hit_rate": round(cache_effectiveness.get('hit_rate', 0), 1),
                "total_errors": len(errors),
                "unique_files": len(top_files)
            }
        }
    except Exception as e:
        return {
            "error": str(e),
            "period": days,
            "file_types": {},
            "top_files": [],
            "hourly_distribution": {},
            "cache_effectiveness": {},
            "errors": [],
            "output_formats": {"pdf": 0, "html": 0}
        }

@router.get("/daily/{date}")
async def get_daily_stats(request: Request, date: date):
    """특정 날짜 통계"""
    db = request.app.state.stats_db
    return db.get_daily_stats(date)

@router.get("/export")
async def export_stats(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    format: str = Query("json", regex="^(json|csv)$")
):
    """통계 데이터 내보내기"""
    db = request.app.state.stats_db
    stats = db.get_period_stats(start_date, end_date)
    
    if format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        if stats:
            writer = csv.DictWriter(output, fieldnames=stats[0].keys())
            writer.writeheader()
            writer.writerows(stats)
        
        from fastapi.responses import Response
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=stats_{start_date}_{end_date}.csv"}
        )
    
    return stats