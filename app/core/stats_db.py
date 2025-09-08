"""
SQLite 기반 문서 변환 통계 시스템
stats_db.py
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Any
from contextlib import contextmanager
import json

from app.core.logger import get_logger

logger = get_logger(__name__)


class StatsDatabase:
    """문서 변환 통계 데이터베이스"""
    
    def __init__(self, db_path: str = "stats.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # dict처럼 접근 가능
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """데이터베이스 초기화"""
        with self.get_connection() as conn:
            # 변환 이력 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,  -- 'url' or 'path'
                    source_value TEXT NOT NULL,  -- URL 또는 파일 경로
                    file_name TEXT,
                    file_type TEXT,  -- 확장자
                    file_size INTEGER,
                    output_format TEXT,  -- 'pdf' or 'html'
                    conversion_time REAL,  -- 변환 소요 시간(초)
                    cache_hit BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_ip TEXT,
                    user_agent TEXT,
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT
                )
            """)
            
            # 인덱스 생성 (통계 쿼리 최적화)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversions_date 
                ON conversions(DATE(created_at))
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversions_file_type 
                ON conversions(file_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversions_source 
                ON conversions(source_type, source_value)
            """)
            
            # 일별 집계 테이블 (성능 최적화)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date DATE PRIMARY KEY,
                    total_conversions INTEGER DEFAULT 0,
                    total_size_mb REAL DEFAULT 0,
                    unique_files INTEGER DEFAULT 0,
                    cache_hit_rate REAL DEFAULT 0,
                    avg_conversion_time REAL DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    stats_json TEXT,  -- 상세 통계 JSON
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def log_conversion(self, 
                      source_type: str,
                      source_value: str,
                      file_name: str,
                      file_type: str,
                      file_size: int,
                      output_format: str,
                      conversion_time: float,
                      cache_hit: bool = False,
                      user_ip: str = None,
                      user_agent: str = None,
                      success: bool = True,
                      error_message: str = None) -> int:
        """변환 작업 로깅"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO conversions (
                    source_type, source_value, file_name, file_type,
                    file_size, output_format, conversion_time, cache_hit,
                    user_ip, user_agent, success, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_type, source_value, file_name, file_type,
                file_size, output_format, conversion_time, cache_hit,
                user_ip, user_agent, success, error_message
            ))
            
            # 일별 통계 업데이트 트리거
            self._update_daily_stats(conn, datetime.now().date())
            
            return cursor.lastrowid
    
    def _update_daily_stats(self, conn, date):
        """일별 통계 업데이트 (내부 함수)"""
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(file_size) / 1048576.0 as size_mb,
                COUNT(DISTINCT source_value) as unique_files,
                AVG(CASE WHEN cache_hit THEN 100.0 ELSE 0.0 END) as cache_rate,
                AVG(conversion_time) as avg_time,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
            FROM conversions
            WHERE DATE(created_at) = ?
        """, (date,)).fetchone()
        
        # 파일 타입별 통계
        type_stats = conn.execute("""
            SELECT 
                file_type,
                COUNT(*) as count,
                SUM(file_size) / 1048576.0 as size_mb
            FROM conversions
            WHERE DATE(created_at) = ?
            GROUP BY file_type
        """, (date,)).fetchall()
        
        stats_json = json.dumps({
            'by_type': {row['file_type']: {
                'count': row['count'],
                'size_mb': row['size_mb']
            } for row in type_stats}
        })
        
        conn.execute("""
            INSERT OR REPLACE INTO daily_stats 
            (date, total_conversions, total_size_mb, unique_files, 
             cache_hit_rate, avg_conversion_time, error_count, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, stats['total'], stats['size_mb'], stats['unique_files'],
            stats['cache_rate'], stats['avg_time'], stats['errors'], stats_json
        ))
    
    # ===== 통계 조회 함수들 =====
    
    def get_daily_stats(self, date: datetime.date) -> Dict[str, Any]:
        """특정 날짜 통계 조회"""
        with self.get_connection() as conn:
            # 캐시된 일별 통계 먼저 확인
            cached = conn.execute("""
                SELECT * FROM daily_stats WHERE date = ?
            """, (date,)).fetchone()
            
            if cached:
                result = dict(cached)
                result['stats_json'] = json.loads(result['stats_json'])
                return result
            
            # 캐시 없으면 실시간 계산
            return self._calculate_daily_stats(conn, date)
    
    def get_period_stats(self, start_date: datetime.date, end_date: datetime.date) -> List[Dict]:
        """기간별 통계 조회"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM daily_stats 
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC
            """, (start_date, end_date)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_file_type_stats(self, days: int = 30) -> Dict[str, Dict]:
        """파일 타입별 통계"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    file_type,
                    COUNT(*) as total_count,
                    SUM(file_size) / 1048576.0 as total_size_mb,
                    AVG(conversion_time) as avg_time,
                    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as cache_hit_rate,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count
                FROM conversions
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY file_type
                ORDER BY total_count DESC
            """, (days,)).fetchall()
            
            return {
                row['file_type']: {
                    'count': row['total_count'],
                    'size_mb': round(row['total_size_mb'], 2),
                    'avg_time': round(row['avg_time'], 2),
                    'cache_hit_rate': round(row['cache_hit_rate'], 1),
                    'error_count': row['error_count']
                } for row in rows
            }
    
    def get_top_files(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """가장 많이 변환된 파일 TOP N"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    source_value,
                    file_name,
                    file_type,
                    COUNT(*) as conversion_count,
                    MAX(created_at) as last_converted
                FROM conversions
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY source_value
                ORDER BY conversion_count DESC
                LIMIT ?
            """, (days, limit)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_hourly_distribution(self, days: int = 7) -> Dict[int, int]:
        """시간대별 사용량 분포"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    CAST(strftime('%H', created_at) AS INTEGER) as hour,
                    COUNT(*) as count
                FROM conversions
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY hour
                ORDER BY hour
            """, (days,)).fetchall()
            
            return {row['hour']: row['count'] for row in rows}
    
    def get_cache_effectiveness(self, days: int = 30) -> Dict[str, Any]:
        """캐시 효율성 분석"""
        with self.get_connection() as conn:
            result = conn.execute("""
                SELECT 
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as hit_rate,
                    SUM(CASE WHEN cache_hit THEN 0 ELSE conversion_time END) as time_saved,
                    SUM(CASE WHEN cache_hit THEN 0 ELSE file_size END) / 1048576.0 as bandwidth_saved_mb
                FROM conversions
                WHERE created_at >= datetime('now', '-' || ? || ' days')
            """, (days,)).fetchone()
            
            return dict(result)
    
    def get_error_stats(self, days: int = 7) -> List[Dict]:
        """에러 통계"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    DATE(created_at) as date,
                    error_message,
                    file_type,
                    COUNT(*) as count
                FROM conversions
                WHERE success = 0 
                    AND created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY date, error_message, file_type
                ORDER BY date DESC, count DESC
            """, (days,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """오래된 데이터 정리"""
        with self.get_connection() as conn:
            deleted = conn.execute("""
                DELETE FROM conversions
                WHERE created_at < datetime('now', '-' || ? || ' days')
            """, (days_to_keep,)).rowcount
            
            # VACUUM으로 공간 회수
            conn.execute("VACUUM")
            
            logger.info(f"오래된 데이터 {deleted}건 삭제 완료")
            return deleted


# ===== 통계 API 라우트 예제 =====
from fastapi import APIRouter, Query, Request
from datetime import datetime, date

stats_router = APIRouter(prefix="/stats", tags=["statistics"])

@stats_router.get("/dashboard")
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

@stats_router.get("/daily/{date}")
async def get_daily_stats(request: Request, date: date):
    """특정 날짜 통계"""
    db = request.app.state.stats_db
    return db.get_daily_stats(date)

@stats_router.get("/export")
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