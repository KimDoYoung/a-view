#!/usr/bin/env python3
"""
async_test.py - 비동기 처리 성능 테스트

현재 utils.py의 동기 처리와 개선된 비동기 처리의 성능을 비교 테스트합니다.
- 대용량 파일 vs 소용량 파일 처리 시간 비교
- 동시 요청 처리 성능 비교
- 캐시 효과 확인

실행 방법:
python async_test.py
"""

import asyncio
import time
import tempfile
import shutil
import hashlib
from pathlib import Path
from typing import Tuple
import aiofiles
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

# 테스트용 가짜 Redis 클라이언트
class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expiry = {}
    
    def hgetall(self, key):
        return self.data.get(key, {})
    
    def hset(self, key, mapping):
        self.data[key] = mapping
    
    def expire(self, key, seconds):
        self.expiry[key] = time.time() + seconds

# 테스트용 설정
class TestConfig:
    def __init__(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.CACHE_DIR = self.temp_dir / "cache"
        self.CONVERTED_DIR = self.temp_dir / "converted"
        self.CACHE_DIR.mkdir(exist_ok=True)
        self.CONVERTED_DIR.mkdir(exist_ok=True)
        self.HOST = "localhost"
        self.PORT = 8003

# 테스트 파일 생성 함수들
def create_test_files(config: TestConfig) -> Tuple[Path, Path, Path]:
    """테스트용 파일들 생성: 소용량, 대용량, CSV"""
    
    # 1. 소용량 텍스트 파일 (1KB)
    small_file = config.temp_dir / "small.txt"
    small_content = "작은 파일 테스트\n" * 50
    small_file.write_text(small_content, encoding='utf-8')
    
    # 2. 대용량 텍스트 파일 (1MB)
    large_file = config.temp_dir / "large.txt"
    large_content = "대용량 파일 테스트 " * 50000
    large_file.write_text(large_content, encoding='utf-8')
    
    # 3. CSV 파일 (중간 크기)
    csv_file = config.temp_dir / "test.csv"
    # 1000행의 CSV 데이터 생성
    data = {
        'ID': range(1, 1001),
        '이름': [f'사용자{i}' for i in range(1, 1001)],
        '점수': [i % 100 for i in range(1, 1001)],
        '등급': ['A' if i % 100 > 80 else 'B' if i % 100 > 60 else 'C' for i in range(1, 1001)]
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    
    print(f"테스트 파일 생성 완료:")
    print(f"  소용량: {small_file} ({small_file.stat().st_size:,} bytes)")
    print(f"  대용량: {large_file} ({large_file.stat().st_size:,} bytes)")
    print(f"  CSV: {csv_file} ({csv_file.stat().st_size:,} bytes)")
    
    return small_file, large_file, csv_file

# 현재 utils.py 스타일의 동기 처리 함수들
class SyncProcessor:
    def __init__(self, config: TestConfig):
        self.config = config
        self.redis = FakeRedis()
    
    def process_file(self, file_path: Path, output_format: str = "html") -> Tuple[float, Path]:
        """동기적 파일 처리"""
        start_time = time.time()
        
        # 1. 파일 복사 (캐시 시뮬레이션)
        cache_key = hashlib.md5(str(file_path).encode()).hexdigest()
        cached_path = self.config.CACHE_DIR / f"{cache_key}{file_path.suffix}"
        
        # 캐시 확인
        cached_info = self.redis.hgetall(f"test:{cache_key}")
        if cached_info and Path(cached_info.get('path', '')).exists():
            print(f"  캐시 히트: {file_path.name}")
            return time.time() - start_time, Path(cached_info['path'])
        
        # 파일 복사 (동기)
        shutil.copy2(file_path, cached_path)
        
        # Redis 캐시 저장
        self.redis.hset(f"test:{cache_key}", {
            'path': str(cached_path),
            'filename': file_path.name
        })
        
        # 2. 변환 처리 (HTML 시뮬레이션)
        if output_format == "html":
            output_path = self.config.CONVERTED_DIR / f"{cached_path.stem}.html"
            if not output_path.exists():
                # 텍스트 파일을 HTML로 변환 (시뮬레이션)
                content = cached_path.read_text(encoding='utf-8')
                html_content = f"<html><body><pre>{content}</pre></body></html>"
                output_path.write_text(html_content, encoding='utf-8')
        
        processing_time = time.time() - start_time
        print(f"  동기 처리 완료: {file_path.name} ({processing_time:.3f}초)")
        return processing_time, output_path

# 개선된 비동기 처리 함수들
class AsyncProcessor:
    def __init__(self, config: TestConfig):
        self.config = config
        self.redis = FakeRedis()
        self.semaphore = asyncio.Semaphore(3)  # 동시 처리 제한
    
    async def process_file(self, file_path: Path, output_format: str = "html") -> Tuple[float, Path]:
        """비동기적 파일 처리"""
        async with self.semaphore:
            start_time = time.time()
            
            # 1. 파일 복사 (비동기)
            cache_key = hashlib.md5(str(file_path).encode()).hexdigest()
            cached_path = self.config.CACHE_DIR / f"{cache_key}_async{file_path.suffix}"
            
            # 캐시 확인
            cached_info = self.redis.hgetall(f"test_async:{cache_key}")
            if cached_info and Path(cached_info.get('path', '')).exists():
                print(f"  비동기 캐시 히트: {file_path.name}")
                return time.time() - start_time, Path(cached_info['path'])
            
            # 비동기 파일 복사
            await self._async_copy_file(file_path, cached_path)
            
            # Redis 캐시 저장
            self.redis.hset(f"test_async:{cache_key}", {
                'path': str(cached_path),
                'filename': file_path.name
            })
            
            # 2. 변환 처리 (비동기)
            if output_format == "html":
                output_path = self.config.CONVERTED_DIR / f"{cached_path.stem}_async.html"
                if not output_path.exists():
                    await self._async_convert_to_html(cached_path, output_path)
            
            processing_time = time.time() - start_time
            print(f"  비동기 처리 완료: {file_path.name} ({processing_time:.3f}초)")
            return processing_time, output_path
    
    async def _async_copy_file(self, src: Path, dst: Path):
        """비동기 파일 복사"""
        async with aiofiles.open(src, 'rb') as src_f:
            content = await src_f.read()
        async with aiofiles.open(dst, 'wb') as dst_f:
            await dst_f.write(content)
    
    async def _async_convert_to_html(self, input_path: Path, output_path: Path):
        """비동기 HTML 변환"""
        # CPU 집약적 작업을 별도 스레드에서 실행
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(executor, self._convert_sync, input_path, output_path)
    
    def _convert_sync(self, input_path: Path, output_path: Path):
        """동기적 변환 작업 (스레드에서 실행)"""
        content = input_path.read_text(encoding='utf-8')
        html_content = f"<html><body><pre>{content}</pre></body></html>"
        output_path.write_text(html_content, encoding='utf-8')

# 테스트 실행 함수들
async def test_single_file_processing():
    """단일 파일 처리 성능 테스트"""
    print("\n=== 단일 파일 처리 성능 테스트 ===")
    
    config = TestConfig()
    small_file, large_file, csv_file = create_test_files(config)
    
    sync_processor = SyncProcessor(config)
    async_processor = AsyncProcessor(config)
    
    test_files = [
        ("소용량 파일", small_file),
        ("대용량 파일", large_file),
        ("CSV 파일", csv_file)
    ]
    
    for file_desc, file_path in test_files:
        print(f"\n{file_desc} 테스트:")
        
        # 동기 처리
        sync_time, _ = sync_processor.process_file(file_path)
        
        # 비동기 처리
        async_time, _ = await async_processor.process_file(file_path)
        
        # 결과 비교
        improvement = ((sync_time - async_time) / sync_time) * 100 if sync_time > 0 else 0
        print(f"  동기 처리: {sync_time:.3f}초")
        print(f"  비동기 처리: {async_time:.3f}초")
        print(f"  성능 개선: {improvement:+.1f}%")

async def test_concurrent_processing():
    """동시 처리 성능 테스트"""
    print("\n=== 동시 처리 성능 테스트 ===")
    
    config = TestConfig()
    small_file, large_file, csv_file = create_test_files(config)
    
    # 시나리오: A(대용량), B(소용량), C(CSV) 동시 처리
    test_scenario = [
        ("A사용자(대용량)", large_file),
        ("B사용자(소용량)", small_file),
        ("C사용자(CSV)", csv_file)
    ]
    
    print("\n동기 처리 (순차 실행):")
    sync_processor = SyncProcessor(config)
    sync_start = time.time()
    sync_results = []
    
    for user, file_path in test_scenario:
        start = time.time()
        processing_time, _ = sync_processor.process_file(file_path)
        end = time.time()
        sync_results.append((user, end - sync_start))
        print(f"  {user}: {end - sync_start:.3f}초에 완료")
    
    sync_total = time.time() - sync_start
    print(f"전체 소요시간: {sync_total:.3f}초")
    
    print("\n비동기 처리 (동시 실행):")
    async_processor = AsyncProcessor(config)
    async_start = time.time()
    
    # 각 사용자별로 태스크 생성
    user_tasks = {}
    for user, file_path in test_scenario:
        task = asyncio.create_task(async_processor.process_file(file_path))
        user_tasks[user] = task
    
    # 완료 순서 추적 - gather 사용으로 결과를 순서대로 받기
    async_results = []
    
    # 모든 태스크를 동시에 실행하고 완료 시점을 개별적으로 추적
    pending_tasks = set(user_tasks.values())
    user_to_task = {task: user for user, task in user_tasks.items()}
    
    while pending_tasks:
        done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for completed_task in done:
            completion_time = time.time() - async_start
            user = user_to_task[completed_task]
            
            try:
                processing_time, _ = await completed_task
                async_results.append((user, completion_time))
                print(f"  {user}: {completion_time:.3f}초에 완료")
            except Exception as e:
                print(f"  {user}: 오류 발생 - {e}")
    
    async_total = time.time() - async_start
    print(f"전체 소요시간: {async_total:.3f}초")
    
    # 결과 비교
    improvement = ((sync_total - async_total) / sync_total) * 100
    print(f"\n동시 처리 성능 개선: {improvement:.1f}%")
    
    # 완료 순서 비교
    print(f"\n완료 순서 비교:")
    print("동기 처리:", " → ".join([user for user, _ in sync_results]))
    print("비동기 처리:", " → ".join([user for user, _ in sorted(async_results, key=lambda x: x[1])]))

async def test_cache_effectiveness():
    """캐시 효과 테스트"""
    print("\n=== 캐시 효과 테스트 ===")
    
    config = TestConfig()
    small_file, large_file, csv_file = create_test_files(config)
    
    async_processor = AsyncProcessor(config)
    
    print("첫 번째 처리 (캐시 없음):")
    time1, _ = await async_processor.process_file(large_file)
    
    print("두 번째 처리 (캐시 있음):")
    time2, _ = await async_processor.process_file(large_file)
    
    cache_improvement = ((time1 - time2) / time1) * 100
    print(f"캐시로 인한 성능 개선: {cache_improvement:.1f}%")

def cleanup_test_files(config: TestConfig):
    """테스트 파일 정리"""
    if config.temp_dir.exists():
        shutil.rmtree(config.temp_dir)
        print(f"\n테스트 파일 정리 완료: {config.temp_dir}")

async def main():
    """메인 테스트 실행"""
    print("비동기 처리 성능 테스트 시작")
    print("=" * 50)
    
    config = TestConfig()
    
    try:
        # 1. 단일 파일 처리 테스트
        await test_single_file_processing()
        
        # 2. 동시 처리 테스트
        await test_concurrent_processing()
        
        # 3. 캐시 효과 테스트
        await test_cache_effectiveness()
        
        print("\n" + "=" * 50)
        print("테스트 완료!")
        
    except Exception as e:
        print(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cleanup_test_files(config)

if __name__ == "__main__":
    # 필요한 라이브러리 설치 확인
    try:
        import aiofiles
        import pandas as pd
    except ImportError as e:
        print(f"필요한 라이브러리를 설치해주세요: pip install aiofiles pandas")
        print(f"누락된 라이브러리: {e}")
        exit(1)
    
    # 테스트 실행
    asyncio.run(main())