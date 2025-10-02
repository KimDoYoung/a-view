#!/usr/bin/env python3
"""
cleanup_old_cache_files 함수 테스트 스크립트

사용법:
    python test_cleanup_file.py [옵션]

옵션:
    --hours N          N시간 이상된 파일 삭제 (기본값: 24)
    --dry-run          실제 삭제하지 않고 시뮬레이션만 실행
    --create-test      테스트용 더미 파일들 생성
    --verbose          상세 로그 출력
    --help             도움말 표시

예시:
    python test_cleanup_file.py --create-test --verbose
    python test_cleanup_file.py --hours 1 --dry-run
    python test_cleanup_file.py --hours 24
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# A-View 모듈들 import
try:
    from app.core.config import settings
    from app.core.logger import get_logger
except ImportError as e:
    print(f"❌ A-View 모듈을 import할 수 없습니다: {e}")
    print("프로젝트 루트에서 실행하거나 PYTHONPATH를 설정해주세요.")
    sys.exit(1)

logger = get_logger(__name__)

def create_test_files(cache_dir: Path, converted_dir: Path, count: int = 10):
    """테스트용 더미 파일들 생성"""
    print(f"🔧 테스트용 더미 파일 생성 중...")
    
    # 디렉토리 생성
    cache_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)
    
    current_time = time.time()
    created_files = []
    
    # 다양한 시간대의 파일들 생성
    test_scenarios = [
        ("very_old", 48),      # 48시간 전
        ("old", 25),           # 25시간 전  
        ("recent", 12),        # 12시간 전
        ("new", 1),            # 1시간 전
        ("very_new", 0.1),     # 6분 전
    ]
    
    for scenario, hours_ago in test_scenarios:
        for i in range(count // len(test_scenarios) + 1):
            # 캐시 파일 생성
            cache_file = cache_dir / f"test_{scenario}_{i}_cache.txt"
            with open(cache_file, 'w') as f:
                f.write(f"Test cache file - {scenario} - {i}\nCreated: {datetime.now()}")
            
            # 변환된 파일 생성
            converted_file = converted_dir / f"test_{scenario}_{i}_converted.html"
            with open(converted_file, 'w') as f:
                f.write(f"<html><body>Test converted file - {scenario} - {i}</body></html>")
            
            # 파일 수정 시간 변경
            file_time = current_time - (hours_ago * 3600)
            os.utime(cache_file, (file_time, file_time))
            os.utime(converted_file, (file_time, file_time))
            
            created_files.extend([cache_file, converted_file])
    
    print(f"✅ {len(created_files)}개의 테스트 파일 생성 완료")
    return created_files

def analyze_files(cache_dir: Path, converted_dir: Path, max_age_hours: int):
    """파일 분석 및 통계 출력"""
    print(f"\n📊 파일 분석 (기준: {max_age_hours}시간)")
    print("=" * 60)
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    total_files = 0
    old_files = 0
    recent_files = 0
    total_size = 0
    old_size = 0
    
    # 캐시 디렉토리 분석
    if cache_dir.exists():
        print(f"\n📁 캐시 디렉토리: {cache_dir}")
        for cache_file in cache_dir.rglob("*"):
            if cache_file.is_file():
                file_stat = cache_file.stat()
                file_age = current_time - file_stat.st_mtime
                file_size = file_stat.st_size
                
                total_files += 1
                total_size += file_size
                
                age_hours = file_age / 3600
                age_str = f"{age_hours:.1f}시간"
                
                if file_age > max_age_seconds:
                    old_files += 1
                    old_size += file_size
                    status = "🗑️  삭제 대상"
                else:
                    recent_files += 1
                    status = "✅ 유지"
                
                print(f"  {cache_file.name:<30} {age_str:>10} {file_size:>8}B {status}")
    
    # 변환된 파일 디렉토리 분석
    if converted_dir.exists():
        print(f"\n📁 변환된 파일 디렉토리: {converted_dir}")
        for converted_file in converted_dir.rglob("*"):
            if converted_file.is_file():
                file_stat = converted_file.stat()
                file_age = current_time - file_stat.st_mtime
                file_size = file_stat.st_size
                
                total_files += 1
                total_size += file_size
                
                age_hours = file_age / 3600
                age_str = f"{age_hours:.1f}시간"
                
                if file_age > max_age_seconds:
                    old_files += 1
                    old_size += file_size
                    status = "🗑️  삭제 대상"
                else:
                    recent_files += 1
                    status = "✅ 유지"
                
                print(f"  {converted_file.name:<30} {age_str:>10} {file_size:>8}B {status}")
    
    # 요약 통계
    print(f"\n📈 요약 통계")
    print("=" * 40)
    print(f"전체 파일:     {total_files:>6}개")
    print(f"삭제 대상:     {old_files:>6}개")
    print(f"유지 대상:     {recent_files:>6}개")
    print(f"전체 크기:     {total_size:>6}B")
    print(f"삭제될 크기:   {old_size:>6}B")
    
    return old_files, old_size

def cleanup_old_cache_files_with_logging(max_age_hours: int = 24, dry_run: bool = False):
    """로깅이 추가된 cleanup_old_cache_files 함수"""
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    deleted_files = []
    deleted_size = 0
    failed_deletions = []
    
    cache_dir = Path(settings.CACHE_DIR)
    converted_dir = Path(settings.CONVERTED_DIR)
    
    print(f"\n🧹 캐시 정리 시작 ({'DRY RUN' if dry_run else 'REAL RUN'})")
    print("=" * 50)
    
    # 캐시 파일 정리
    if cache_dir.exists():
        print(f"📁 캐시 디렉토리 정리: {cache_dir}")
        for cache_file in cache_dir.rglob("*"):
            if cache_file.is_file():
                file_age = current_time - cache_file.stat().st_mtime
                if file_age > max_age_seconds:
                    file_size = cache_file.stat().st_size
                    age_hours = file_age / 3600
                    
                    if dry_run:
                        print(f"  [DRY] 삭제 예정: {cache_file.name} ({age_hours:.1f}시간 전)")
                        deleted_files.append(cache_file)
                        deleted_size += file_size
                    else:
                        try:
                            cache_file.unlink()
                            print(f"  ✅ 삭제 완료: {cache_file.name} ({age_hours:.1f}시간 전)")
                            deleted_files.append(cache_file)
                            deleted_size += file_size
                        except Exception as e:
                            print(f"  ❌ 삭제 실패: {cache_file.name} - {e}")
                            failed_deletions.append((cache_file, str(e)))

    # 변환된 파일 정리
    if converted_dir.exists():
        print(f"📁 변환된 파일 디렉토리 정리: {converted_dir}")
        for converted_file in converted_dir.rglob("*"):
            if converted_file.is_file():
                file_age = current_time - converted_file.stat().st_mtime
                if file_age > max_age_seconds:
                    file_size = converted_file.stat().st_size
                    age_hours = file_age / 3600
                    
                    if dry_run:
                        print(f"  [DRY] 삭제 예정: {converted_file.name} ({age_hours:.1f}시간 전)")
                        deleted_files.append(converted_file)
                        deleted_size += file_size
                    else:
                        try:
                            converted_file.unlink()
                            print(f"  ✅ 삭제 완료: {converted_file.name} ({age_hours:.1f}시간 전)")
                            deleted_files.append(converted_file)
                            deleted_size += file_size
                        except Exception as e:
                            print(f"  ❌ 삭제 실패: {converted_file.name} - {e}")
                            failed_deletions.append((converted_file, str(e)))
    
    # 결과 요약
    print(f"\n📋 정리 결과")
    print("=" * 30)
    print(f"{'삭제 예정' if dry_run else '삭제 완료'}: {len(deleted_files)}개 파일")
    print(f"총 크기:       {deleted_size}B ({deleted_size/1024:.1f}KB)")
    print(f"실패:         {len(failed_deletions)}개 파일")
    
    if failed_deletions:
        print(f"\n❌ 삭제 실패 파일들:")
        for failed_file, error in failed_deletions:
            print(f"  {failed_file}: {error}")
    
    return len(deleted_files), deleted_size, failed_deletions

def main():
    parser = argparse.ArgumentParser(
        description="cleanup_old_cache_files 함수 테스트 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument("--hours", type=int, default=24,
                        help="N시간 이상된 파일 삭제 (기본값: 24)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 삭제하지 않고 시뮬레이션만 실행")
    parser.add_argument("--create-test", action="store_true",
                        help="테스트용 더미 파일들 생성")
    parser.add_argument("--verbose", action="store_true",
                        help="상세 로그 출력")
    
    args = parser.parse_args()
    
    # 설정 정보 출력
    print("🚀 A-View 캐시 정리 테스트")
    print("=" * 50)
    print(f"캐시 디렉토리:     {settings.CACHE_DIR}")
    print(f"변환 디렉토리:     {settings.CONVERTED_DIR}")
    print(f"최대 보관 시간:    {args.hours}시간")
    print(f"실행 모드:         {'DRY RUN' if args.dry_run else 'REAL RUN'}")
    print(f"현재 시간:         {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    cache_dir = Path(settings.CACHE_DIR)
    converted_dir = Path(settings.CONVERTED_DIR)
    
    # 테스트 파일 생성 (옵션)
    if args.create_test:
        create_test_files(cache_dir, converted_dir)
    
    # 파일 분석 (옵션)
    if args.verbose:
        analyze_files(cache_dir, converted_dir, args.hours)
    
    # 캐시 정리 실행
    deleted_count, deleted_size, failed_deletions = cleanup_old_cache_files_with_logging(
        max_age_hours=args.hours,
        dry_run=args.dry_run
    )
    
    # 최종 결과
    print(f"\n🎯 최종 결과")
    print("=" * 30)
    if args.dry_run:
        print(f"✅ DRY RUN 완료 - {deleted_count}개 파일이 삭제 예정입니다.")
        if deleted_count > 0:
            print(f"실제 삭제하려면: python {__file__} --hours {args.hours}")
    else:
        print(f"✅ 캐시 정리 완료 - {deleted_count}개 파일을 삭제했습니다.")
        if failed_deletions:
            print(f"⚠️  {len(failed_deletions)}개 파일 삭제에 실패했습니다.")
    
    return 0 if len(failed_deletions) == 0 else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류 발생: {e}")
        if "--verbose" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)