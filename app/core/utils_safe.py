"""
스케줄러용 안전한 캐시 정리 함수
기존 utils.py의 cleanup_old_cache_files를 대체하는 안전한 버전
"""

import time
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

def cleanup_old_cache_files_safe(max_age_hours: int = 24, timeout_seconds: int = 300):
    """
    스케줄러용 안전한 캐시 정리 함수
    
    Args:
        max_age_hours: 삭제할 파일의 최소 나이 (시간)
        timeout_seconds: 최대 실행 시간 (초)
    
    Returns:
        dict: 정리 결과 통계
    """
    start_time = time.time()
    
    try:
        logger.info(f"🧹 안전한 캐시 정리 시작 (기준: {max_age_hours}시간, 타임아웃: {timeout_seconds}초)")
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        deleted_files = []
        deleted_size = 0
        failed_deletions = []
        processed_dirs = []
        
        cache_dir = Path(settings.CACHE_DIR)
        converted_dir = Path(settings.CONVERTED_DIR)
        
        # 캐시 디렉토리 정리
        if cache_dir.exists():
            logger.info(f"📁 캐시 디렉토리 정리: {cache_dir}")
            processed_dirs.append(str(cache_dir))
            
            try:
                for cache_file in cache_dir.rglob("*"):
                    # 타임아웃 체크
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"⏰ 캐시 정리 타임아웃 ({timeout_seconds}초)")
                        break
                        
                    if cache_file.is_file():
                        try:
                            file_age = current_time - cache_file.stat().st_mtime
                            if file_age > max_age_seconds:
                                file_size = cache_file.stat().st_size
                                cache_file.unlink()
                                deleted_files.append(str(cache_file))
                                deleted_size += file_size
                                logger.debug(f"✅ 삭제: {cache_file.name}")
                        except OSError as e:
                            error_msg = f"캐시 파일 삭제 실패: {cache_file} - {e}"
                            logger.warning(error_msg)
                            failed_deletions.append(error_msg)
                        except Exception as e:
                            error_msg = f"예상치 못한 오류: {cache_file} - {e}"
                            logger.error(error_msg)
                            failed_deletions.append(error_msg)
                            
            except Exception as e:
                error_msg = f"캐시 디렉토리 처리 중 오류: {e}"
                logger.error(error_msg)
                failed_deletions.append(error_msg)

        # 변환된 파일 디렉토리 정리
        if converted_dir.exists():
            logger.info(f"📁 변환된 파일 디렉토리 정리: {converted_dir}")
            processed_dirs.append(str(converted_dir))
            
            try:
                for converted_file in converted_dir.rglob("*"):
                    # 타임아웃 체크
                    if time.time() - start_time > timeout_seconds:
                        logger.warning(f"⏰ 변환 파일 정리 타임아웃 ({timeout_seconds}초)")
                        break
                        
                    if converted_file.is_file():
                        try:
                            file_age = current_time - converted_file.stat().st_mtime
                            if file_age > max_age_seconds:
                                file_size = converted_file.stat().st_size
                                converted_file.unlink()
                                deleted_files.append(str(converted_file))
                                deleted_size += file_size
                                logger.debug(f"✅ 삭제: {converted_file.name}")
                        except OSError as e:
                            error_msg = f"변환 파일 삭제 실패: {converted_file} - {e}"
                            logger.warning(error_msg)
                            failed_deletions.append(error_msg)
                        except Exception as e:
                            error_msg = f"예상치 못한 오류: {converted_file} - {e}"
                            logger.error(error_msg)
                            failed_deletions.append(error_msg)
                            
            except Exception as e:
                error_msg = f"변환 파일 디렉토리 처리 중 오류: {e}"
                logger.error(error_msg)
                failed_deletions.append(error_msg)

        # 결과 계산
        execution_time = time.time() - start_time
        results = {
            'deleted_count': len(deleted_files),
            'deleted_size': deleted_size,
            'failed_count': len(failed_deletions),
            'execution_time': execution_time,
            'processed_dirs': processed_dirs,
            'max_age_hours': max_age_hours,
            'timeout_seconds': timeout_seconds,
            'completed_normally': execution_time <= timeout_seconds
        }
        
        # 결과 로깅
        logger.info("📊 캐시 정리 완료:")
        logger.info(f"  - 삭제된 파일: {len(deleted_files)}개")
        logger.info(f"  - 삭제된 용량: {deleted_size:,}B ({deleted_size/1024:.1f}KB)")
        logger.info(f"  - 실패한 삭제: {len(failed_deletions)}개")
        logger.info(f"  - 실행 시간: {execution_time:.2f}초")
        
        if failed_deletions:
            logger.warning("⚠️  삭제 실패 목록:")
            for failure in failed_deletions[:3]:  # 처음 3개만 로깅
                logger.warning(f"  - {failure}")
            if len(failed_deletions) > 3:
                logger.warning(f"  - ... 외 {len(failed_deletions) - 3}개 더")
        
        return results
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"캐시 정리 중 치명적 오류: {type(e).__name__}: {e}"
        logger.error(error_msg)
        
        # 오류가 발생해도 스케줄러가 중단되지 않도록 기본 결과 반환
        return {
            'deleted_count': 0,
            'deleted_size': 0,
            'failed_count': 1,
            'execution_time': execution_time,
            'processed_dirs': [],
            'max_age_hours': max_age_hours,
            'timeout_seconds': timeout_seconds,
            'completed_normally': False,
            'error': error_msg
        }