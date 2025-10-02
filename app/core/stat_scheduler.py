import sqlite3
import threading
import time
from datetime import datetime, timedelta

import schedule

from app.core.config import settings
from app.core.logger import get_logger
from app.core.stats_db import StatsDatabase
from app.core.utils_safe import cleanup_old_cache_files_safe

logger = get_logger(__name__)

class StatsScheduler:
    """통계 스케줄러"""
    
    def __init__(self, stats_manager: StatsDatabase):
        self.stats_manager = stats_manager
        self.scheduler_thread = None
        self.running = False
    
    def start_scheduler(self):
        """스케줄러 시작"""
        if self.running:
            return
        
        # 매일 자정 5분에 전날 통계 재계산
        schedule.every().day.at(settings.EVERY_DAY_AT).do(self._daily_recalculation)

        # 매주 일요일 새벽 2시에 주간 정리
        schedule.every().sunday.at(settings.EVERY_SUNDAY_AT).do(self._weekly_maintenance)

        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
    
    
    def stop_scheduler(self):
        """스케줄러 중지"""
        self.running = False
        schedule.clear()
        print("📅 통계 스케줄러 중지됨")
    
    def _run_scheduler(self):
        """스케줄러 실행 루프"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
    
    def _daily_recalculation(self):
        """매일 자정 실행: 전날 통계 재계산"""
        yesterday = datetime.now().date() - timedelta(days=1)
        logger.info(f"📅 일일 통계 재계산 시작: {yesterday}")
        self.stats_manager.recalculate_daily_stats(yesterday)

        # settings.CACHE_DIR과 settings.CONVERTED_DIR에서 24시간이 지난 캐시 파일 정리
        logger.info("🧹 캐시 디렉토리 & 변환된 파일 정리 시작(24시간 지난 파일)")
        try:
            # 안전한 캐시 정리 함수 사용 (타임아웃: 5분)
            results = cleanup_old_cache_files_safe(max_age_hours=24, timeout_seconds=300)
            logger.info(f"✅ 캐시 정리 완료 - {results['deleted_count']}개 파일 삭제, {results['failed_count']}개 실패")
        except Exception as e:
            logger.error(f"❌ 캐시 정리 중 오류 발생: {e}")
            logger.info("⚠️  캐시 정리 실패했지만 스케줄러는 계속 실행됩니다")

    def _weekly_maintenance(self):
        """주간 유지보수: 오래된 로그 정리 등"""
        # 90일 이전 변환 로그 삭제 (옵션)
        cutoff_date = datetime.now() - timedelta(days=90)
        
        with sqlite3.connect(self.stats_manager.db_path) as conn:
            deleted = conn.execute("""
                DELETE FROM conversions WHERE created_at < ?
            """, (cutoff_date,)).rowcount
            
            print(f"🧹 주간 정리: {deleted}개 오래된 로그 삭제")