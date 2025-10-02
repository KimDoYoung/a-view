#!/usr/bin/env python3
"""
스케줄러용 안전한 캐시 정리 함수 테스트

이 스크립트는 스케줄러에서 실행될 때의 안전성을 테스트합니다:
1. 모든 예외를 잡아서 스케줄러가 중단되지 않도록 함
2. 상세한 로깅으로 문제 추적 가능
3. 통계 정보 제공
4. 타임아웃 처리

사용법:
    python test_scheduler_cleanup.py [옵션]

옵션:
    --hours N          N시간 이상된 파일 삭제 (기본값: 24)
    --timeout N        최대 실행 시간(초) (기본값: 300)
    --verbose          상세 로그 출력
    --simulate         스케줄러 실행 시뮬레이션
"""

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.core.config import settings
    from app.core.logger import get_logger
except ImportError as e:
    print(f"❌ A-View 모듈을 import할 수 없습니다: {e}")
    sys.exit(1)

logger = get_logger(__name__)

class SafeCacheCleanup:
    """스케줄러용 안전한 캐시 정리 클래스"""
    
    def __init__(self, timeout_seconds=300):
        self.timeout_seconds = timeout_seconds
        self.completed = False
        self.error_occurred = False
        self.results = {}
        
    def cleanup_old_cache_files_safe(self, max_age_hours: int = 24):
        """
        스케줄러용 안전한 캐시 정리 함수
        - 모든 예외를 포착하여 스케줄러가 중단되지 않도록 함
        - 타임아웃 처리
        - 상세한 로깅
        """
        start_time = time.time()
        
        try:
            logger.info(f"🧹 안전한 캐시 정리 시작 (기준: {max_age_hours}시간)")
            
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
                        if time.time() - start_time > self.timeout_seconds:
                            logger.warning(f"⏰ 캐시 정리 타임아웃 ({self.timeout_seconds}초)")
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
            else:
                logger.info(f"📁 캐시 디렉토리가 존재하지 않음: {cache_dir}")

            # 변환된 파일 디렉토리 정리
            if converted_dir.exists():
                logger.info(f"📁 변환된 파일 디렉토리 정리: {converted_dir}")
                processed_dirs.append(str(converted_dir))
                
                try:
                    for converted_file in converted_dir.rglob("*"):
                        # 타임아웃 체크
                        if time.time() - start_time > self.timeout_seconds:
                            logger.warning(f"⏰ 변환 파일 정리 타임아웃 ({self.timeout_seconds}초)")
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
            else:
                logger.info(f"📁 변환된 파일 디렉토리가 존재하지 않음: {converted_dir}")

            # 결과 저장
            execution_time = time.time() - start_time
            self.results = {
                'deleted_count': len(deleted_files),
                'deleted_size': deleted_size,
                'failed_count': len(failed_deletions),
                'execution_time': execution_time,
                'processed_dirs': processed_dirs,
                'max_age_hours': max_age_hours,
                'timeout_seconds': self.timeout_seconds,
                'completed_normally': time.time() - start_time <= self.timeout_seconds
            }
            
            # 결과 로깅
            logger.info(f"📊 캐시 정리 완료:")
            logger.info(f"  - 삭제된 파일: {len(deleted_files)}개")
            logger.info(f"  - 삭제된 용량: {deleted_size:,}B ({deleted_size/1024:.1f}KB)")
            logger.info(f"  - 실패한 삭제: {len(failed_deletions)}개")
            logger.info(f"  - 실행 시간: {execution_time:.2f}초")
            
            if failed_deletions:
                logger.warning(f"⚠️  삭제 실패 목록:")
                for failure in failed_deletions[:5]:  # 처음 5개만 로깅
                    logger.warning(f"  - {failure}")
                if len(failed_deletions) > 5:
                    logger.warning(f"  - ... 외 {len(failed_deletions) - 5}개 더")
            
            self.completed = True
            return self.results
            
        except Exception as e:
            self.error_occurred = True
            error_msg = f"캐시 정리 중 치명적 오류: {type(e).__name__}: {e}"
            logger.error(error_msg)
            
            # 기본 결과 반환
            execution_time = time.time() - start_time
            self.results = {
                'deleted_count': 0,
                'deleted_size': 0,
                'failed_count': 1,
                'execution_time': execution_time,
                'processed_dirs': [],
                'max_age_hours': max_age_hours,
                'timeout_seconds': self.timeout_seconds,
                'completed_normally': False,
                'error': error_msg
            }
            return self.results

def run_with_timeout(cleanup_func, timeout_seconds):
    """타임아웃을 가진 실행"""
    result = {'completed': False, 'results': None, 'error': None}
    
    def target():
        try:
            result['results'] = cleanup_func()
            result['completed'] = True
        except Exception as e:
            result['error'] = str(e)
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout_seconds)
    
    if thread.is_alive():
        result['error'] = f"작업이 {timeout_seconds}초 내에 완료되지 않았습니다"
        logger.error(result['error'])
    
    return result

def simulate_scheduler_execution(hours=24, timeout=300):
    """스케줄러 실행 시뮬레이션"""
    print("🤖 스케줄러 실행 시뮬레이션")
    print("=" * 50)
    print(f"현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"캐시 정리 기준: {hours}시간")
    print(f"타임아웃: {timeout}초")
    print()
    
    # 안전한 캐시 정리 실행
    cleanup = SafeCacheCleanup(timeout_seconds=timeout)
    
    print("🧹 캐시 정리 시작...")
    start_time = time.time()
    
    try:
        # 타임아웃을 가진 실행
        result = run_with_timeout(
            lambda: cleanup.cleanup_old_cache_files_safe(hours),
            timeout + 10  # 약간의 여유 시간
        )
        
        execution_time = time.time() - start_time
        
        if result['completed'] and result['results']:
            results = result['results']
            print("✅ 캐시 정리 성공")
            print(f"📊 결과:")
            print(f"  - 삭제된 파일: {results['deleted_count']}개")
            print(f"  - 삭제된 용량: {results['deleted_size']:,}B")
            print(f"  - 실패한 삭제: {results['failed_count']}개")
            print(f"  - 실행 시간: {execution_time:.2f}초")
            print(f"  - 정상 완료: {'Yes' if results['completed_normally'] else 'No'}")
            
            if results['failed_count'] > 0:
                print("⚠️  일부 파일 삭제에 실패했지만 스케줄러는 계속 동작합니다")
            
        else:
            print(f"❌ 캐시 정리 실패: {result.get('error', 'Unknown error')}")
            print("⚠️  스케줄러는 계속 동작하지만 캐시 정리가 실패했습니다")
        
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        print("⚠️  스케줄러는 계속 동작하지만 캐시 정리가 실패했습니다")
    
    print(f"\n⏱️  총 실행 시간: {time.time() - start_time:.2f}초")
    print("🔄 스케줄러 계속 실행 중...")

def main():
    parser = argparse.ArgumentParser(
        description="스케줄러용 안전한 캐시 정리 테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument("--hours", type=int, default=24,
                        help="N시간 이상된 파일 삭제 (기본값: 24)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="최대 실행 시간(초) (기본값: 300)")
    parser.add_argument("--verbose", action="store_true",
                        help="상세 로그 출력")
    parser.add_argument("--simulate", action="store_true",
                        help="스케줄러 실행 시뮬레이션")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel("DEBUG")
    
    print("🛡️  스케줄러용 안전한 캐시 정리 테스트")
    print("=" * 50)
    print(f"캐시 디렉토리: {settings.CACHE_DIR}")
    print(f"변환 디렉토리: {settings.CONVERTED_DIR}")
    print(f"삭제 기준: {args.hours}시간")
    print(f"타임아웃: {args.timeout}초")
    print()
    
    if args.simulate:
        simulate_scheduler_execution(args.hours, args.timeout)
    else:
        cleanup = SafeCacheCleanup(timeout_seconds=args.timeout)
        results = cleanup.cleanup_old_cache_files_safe(args.hours)
        
        print("📋 최종 결과:")
        for key, value in results.items():
            print(f"  {key}: {value}")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류 발생: {e}")
        sys.exit(1)