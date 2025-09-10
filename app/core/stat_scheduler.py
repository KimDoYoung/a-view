from app.core.stats_db import StatsDatabase
import schedule
import threading
import time
import sqlite3
from datetime import datetime, timedelta

from app.core.config import settings

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
        
        print("📅 통계 스케줄러 시작됨")
    
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
        self.stats_manager.recalculate_daily_stats(yesterday)
    
    def _weekly_maintenance(self):
        """주간 유지보수: 오래된 로그 정리 등"""
        # 90일 이전 변환 로그 삭제 (옵션)
        cutoff_date = datetime.now() - timedelta(days=90)
        
        with sqlite3.connect(self.stats_manager.db_path) as conn:
            deleted = conn.execute("""
                DELETE FROM conversions WHERE created_at < ?
            """, (cutoff_date,)).rowcount
            
            print(f"🧹 주간 정리: {deleted}개 오래된 로그 삭제")