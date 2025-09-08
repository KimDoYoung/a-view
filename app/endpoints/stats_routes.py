# ===== 통계 API 라우트 예제 =====
from fastapi import APIRouter, Query, Request
from datetime import date

router = APIRouter()

@router.get("/dashboard")
async def stats_dashboard(request: Request, days: int = Query(7, ge=1, le=365)):
    """통계 대시보드 데이터"""
    db = request.app.state.stats_db
    
    return {
        "period": days,
        "file_types": db.get_file_type_stats(days),
        "top_files": db.get_top_files(days),
        "hourly_distribution": db.get_hourly_distribution(days),
        "cache_effectiveness": db.get_cache_effectiveness(days),
        "errors": db.get_error_stats(days)
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