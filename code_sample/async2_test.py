#!/usr/bin/env python3
"""
async2_test.py - 현실적인 비동기 처리 성능 테스트

실제 utils.py의 주요 병목점들을 시뮬레이션:
1. LibreOffice subprocess 호출 (가장 큰 병목) - 2~10초 소요
2. 네트워크 파일 다운로드 - 1~5초 소요  
3. 파일 I/O 작업 - 0.1~1초 소요
4. Redis 캐시 조회 - 즉시

핵심 질문: A사용자(대용량) vs B사용자(소용량) 동시 요청 시 B가 먼저 완료되는가?

실행 방법:
python async2_test.py
"""

import asyncio
import time
import tempfile
import shutil
import hashlib
import threading
from pathlib import Path
from typing import Tuple, List
from concurrent.futures import ThreadPoolExecutor
import random

# 테스트용 가짜 Redis
class FakeRedis:
    def __init__(self):
        self.data = {}
    
    def hgetall(self, key):
        return self.data.get(key, {})
    
    def hset(self, key, mapping):
        self.data[key] = mapping
    
    def expire(self, key, seconds):
        pass

# 테스트 설정
class TestConfig:
    def __init__(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.CACHE_DIR = self.temp_dir / "cache"
        self.CONVERTED_DIR = self.temp_dir / "converted"
        self.CACHE_DIR.mkdir(exist_ok=True)
        self.CONVERTED_DIR.mkdir(exist_ok=True)

# === 현재 utils.py 방식 (동기 처리) ===
class CurrentUtilsProcessor:
    """현재 utils.py의 동기 처리 방식을 시뮬레이션"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.redis = FakeRedis()
    
    def simulate_libreoffice_subprocess(self, file_size_mb: float) -> float:
        """LibreOffice subprocess.run() 시뮬레이션 - 블로킹!"""
        # 파일 크기에 따른 변환 시간 (실제와 유사하게)
        conversion_time = max(1.0, file_size_mb * 3.0)  # 1MB당 3초
        conversion_time += random.uniform(0.5, 1.5)     # 변동성 추가
        
        thread_id = threading.get_ident()
        print(f"      [LibreOffice] 변환 시작 (스레드:{thread_id}, 예상:{conversion_time:.1f}초)")
        
        # 실제 subprocess.run()처럼 완전히 블로킹
        time.sleep(conversion_time)
        
        print(f"      [LibreOffice] 변환 완료 (소요:{conversion_time:.1f}초)")
        return conversion_time
    
    def simulate_file_download(self, url: str) -> Tuple[float, float]:
        """httpx.get() 다운로드 시뮬레이션 - 블로킹!"""
        if "large" in url:
            download_time = random.uniform(3.0, 5.0)  # 대용량: 3-5초
            file_size_mb = 2.0
        elif "small" in url:
            download_time = random.uniform(0.2, 0.5)  # 소용량: 0.2-0.5초
            file_size_mb = 0.01
        else:
            download_time = random.uniform(1.0, 2.0)  # 중간: 1-2초
            file_size_mb = 0.5
        
        thread_id = threading.get_ident()
        print(f"      [다운로드] 시작 (스레드:{thread_id}, 예상:{download_time:.1f}초)")
        
        # 실제 네트워크 요청처럼 블로킹
        time.sleep(download_time)
        
        print(f"      [다운로드] 완료 (소요:{download_time:.1f}초)")
        return download_time, file_size_mb
    
    def simulate_file_io(self, operation: str, size_mb: float) -> float:
        """파일 I/O 시뮬레이션 - 블로킹!"""
        io_time = max(0.05, size_mb * 0.1)  # 1MB당 0.1초
        
        print(f"      [파일I/O] {operation} (예상:{io_time:.1f}초)")
        time.sleep(io_time)  # 실제 파일 I/O처럼 블로킹
        print(f"      [파일I/O] {operation} 완료")
        return io_time
    
    def process_url_to_pdf(self, url: str, user_name: str) -> Tuple[float, List[str]]:
        """현재 utils.py의 URL -> PDF 변환 과정"""
        start_time = time.time()
        log = []
        thread_id = threading.get_ident()
        
        print(f"  [{user_name}] 동기 처리 시작 (스레드:{thread_id})")
        
        # 1. Redis 캐시 확인 (즉시)
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cached_info = self.redis.hgetall(f"cache:{cache_key}")
        if cached_info:
            total_time = time.time() - start_time
            print(f"  [{user_name}] 캐시 히트! 즉시 완료 ({total_time:.3f}초)")
            return total_time, ["캐시 히트"]
        
        # 2. 파일 다운로드 (블로킹)
        download_time, file_size_mb = self.simulate_file_download(url)
        log.append(f"다운로드: {download_time:.1f}초")
        
        # 3. 파일 저장 (블로킹)
        save_time = self.simulate_file_io("저장", file_size_mb)
        log.append(f"저장: {save_time:.1f}초")
        
        # 4. LibreOffice 변환 (가장 큰 블로킹!)
        conversion_time = self.simulate_libreoffice_subprocess(file_size_mb)
        log.append(f"변환: {conversion_time:.1f}초")
        
        # 5. Redis 캐시 저장
        self.redis.hset(f"cache:{cache_key}", {"path": "/fake/path", "filename": "test.pdf"})
        
        total_time = time.time() - start_time
        print(f"  [{user_name}] 동기 처리 완료! (총 {total_time:.1f}초)")
        return total_time, log

# === 개선된 비동기 처리 ===
class ImprovedAsyncProcessor:
    """개선된 비동기 처리 방식"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.redis = FakeRedis()
        self.conversion_semaphore = asyncio.Semaphore(2)  # LibreOffice 동시 실행 제한
    
    async def simulate_libreoffice_async(self, file_size_mb: float) -> float:
        """LibreOffice를 ThreadPoolExecutor로 비동기화"""
        conversion_time = max(1.0, file_size_mb * 3.0)
        conversion_time += random.uniform(0.5, 1.5)
        
        thread_id = threading.get_ident()
        print(f"      [비동기 LibreOffice] 변환 시작 (스레드:{thread_id}, 예상:{conversion_time:.1f}초)")
        
        # ThreadPoolExecutor로 subprocess를 별도 스레드에서 실행
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(
                executor, 
                lambda: time.sleep(conversion_time)  # 실제로는 subprocess.run()
            )
        
        print(f"      [비동기 LibreOffice] 변환 완료 (소요:{conversion_time:.1f}초)")
        return conversion_time
    
    async def simulate_file_download_async(self, url: str) -> Tuple[float, float]:
        """httpx.AsyncClient 다운로드 시뮬레이션"""
        if "large" in url:
            download_time = random.uniform(3.0, 5.0)
            file_size_mb = 2.0
        elif "small" in url:
            download_time = random.uniform(0.2, 0.5)
            file_size_mb = 0.01
        else:
            download_time = random.uniform(1.0, 2.0)
            file_size_mb = 0.5
        
        print(f"      [비동기 다운로드] 시작 (예상:{download_time:.1f}초)")
        
        # 비동기 sleep으로 네트워크 대기 시뮬레이션
        await asyncio.sleep(download_time)
        
        print(f"      [비동기 다운로드] 완료 (소요:{download_time:.1f}초)")
        return download_time, file_size_mb
    
    async def simulate_file_io_async(self, operation: str, size_mb: float) -> float:
        """aiofiles 파일 I/O 시뮬레이션"""
        io_time = max(0.05, size_mb * 0.1)
        
        print(f"      [비동기 파일I/O] {operation} (예상:{io_time:.1f}초)")
        
        # 비동기 파일 I/O 시뮬레이션
        await asyncio.sleep(io_time)
        
        print(f"      [비동기 파일I/O] {operation} 완료")
        return io_time
    
    async def process_url_to_pdf_async(self, url: str, user_name: str) -> Tuple[float, List[str]]:
        """개선된 비동기 URL -> PDF 변환 과정"""
        start_time = time.time()
        log = []
        
        print(f"  [{user_name}] 비동기 처리 시작")
        
        # 1. Redis 캐시 확인 (즉시)
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cached_info = self.redis.hgetall(f"async_cache:{cache_key}")
        if cached_info:
            total_time = time.time() - start_time
            print(f"  [{user_name}] 캐시 히트! 즉시 완료 ({total_time:.3f}초)")
            return total_time, ["캐시 히트"]
        
        # 2. 파일 다운로드 (비동기)
        download_time, file_size_mb = await self.simulate_file_download_async(url)
        log.append(f"다운로드: {download_time:.1f}초")
        
        # 3. 파일 저장 (비동기)
        save_time = await self.simulate_file_io_async("저장", file_size_mb)
        log.append(f"저장: {save_time:.1f}초")
        
        # 4. LibreOffice 변환 (세마포어로 제한된 비동기)
        async with self.conversion_semaphore:
            conversion_time = await self.simulate_libreoffice_async(file_size_mb)
            log.append(f"변환: {conversion_time:.1f}초")
        
        # 5. Redis 캐시 저장
        self.redis.hset(f"async_cache:{cache_key}", {"path": "/fake/path", "filename": "test.pdf"})
        
        total_time = time.time() - start_time
        print(f"  [{user_name}] 비동기 처리 완료! (총 {total_time:.1f}초)")
        return total_time, log

# === 테스트 시나리오 실행 ===
async def test_concurrent_requests():
    """핵심 테스트: 동시 요청 처리"""
    print("=" * 60)
    print("핵심 테스트: A(대용량) vs B(소용량) vs C(중간) 동시 요청")
    print("=" * 60)
    
    config = TestConfig()
    
    # 테스트 시나리오
    scenarios = [
        ("A사용자(대용량)", "https://example.com/large_file.docx"),
        ("B사용자(소용량)", "https://example.com/small_file.txt"),
        ("C사용자(중간)", "https://example.com/medium_file.pptx")
    ]
    
    # === 동기 처리 테스트 ===
    print("\n🔴 현재 utils.py 방식 (동기 처리):")
    print("→ 순차적으로 처리됨 (A 완료 → B 시작 → C 시작)")
    
    sync_processor = CurrentUtilsProcessor(config)
    sync_start = time.time()
    sync_results = []
    
    for user, url in scenarios:
        user_start = time.time()
        processing_time, log = sync_processor.process_url_to_pdf(url, user)
        completion_time = time.time() - sync_start
        sync_results.append((user, completion_time, log))
        print(f"    ✓ {user}: {completion_time:.1f}초에 완료")
    
    sync_total = time.time() - sync_start
    print(f"동기 처리 전체 시간: {sync_total:.1f}초")
    
    # === 비동기 처리 테스트 ===
    print("\n🟢 개선된 비동기 처리:")
    print("→ 동시 처리됨 (A, B, C 동시 시작)")
    
    async_processor = ImprovedAsyncProcessor(config)
    async_start = time.time()
    
    # 모든 작업을 동시에 시작
    user_tasks = {}
    for user, url in scenarios:
        task = asyncio.create_task(async_processor.process_url_to_pdf_async(url, user))
        user_tasks[user] = task
    
    # 완료 순서 추적 - asyncio.wait 사용
    async_results = []
    pending_tasks = set(user_tasks.values())
    user_to_task = {task: user for user, task in user_tasks.items()}
    
    while pending_tasks:
        done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for completed_task in done:
            completion_time = time.time() - async_start
            user = user_to_task[completed_task]
            
            try:
                processing_time, log = await completed_task
                async_results.append((user, completion_time, log))
                print(f"    ✓ {user}: {completion_time:.1f}초에 완료")
            except Exception as e:
                print(f"    ❌ {user}: 오류 발생 - {e}")
    
    async_total = time.time() - async_start
    print(f"비동기 처리 전체 시간: {async_total:.1f}초")
    
    # === 결과 분석 ===
    print("\n" + "=" * 60)
    print("📊 결과 분석")
    print("=" * 60)
    
    print(f"\n⏱️  전체 처리 시간:")
    print(f"  동기 처리: {sync_total:.1f}초")
    print(f"  비동기 처리: {async_total:.1f}초")
    improvement = ((sync_total - async_total) / sync_total) * 100
    print(f"  성능 개선: {improvement:+.1f}%")
    
    print(f"\n🏁 완료 순서:")
    sync_order = [user for user, _, _ in sync_results]
    async_order = [user for user, _, _ in sorted(async_results, key=lambda x: x[1])]
    
    print(f"  동기 처리: {' → '.join(sync_order)}")
    print(f"  비동기 처리: {' → '.join(async_order)}")
    
    # B사용자가 먼저 완료되었는지 확인
    b_wins_sync = sync_order.index("B사용자(소용량)")
    b_wins_async = async_order.index("B사용자(소용량)")
    
    print(f"\n✨ B사용자(소용량) 순위:")
    print(f"  동기 처리: {b_wins_sync + 1}번째 완료")
    print(f"  비동기 처리: {b_wins_async + 1}번째 완료")
    
    if b_wins_async == 0:
        print("  🎉 비동기에서 B사용자가 1등으로 완료!")
    else:
        print("  ⚠️  비동기에서도 B사용자가 1등이 아님")

async def test_cache_hit_scenario():
    """캐시 히트 시나리오 테스트"""
    print("\n" + "=" * 60)
    print("📦 캐시 효과 테스트")
    print("=" * 60)
    
    config = TestConfig()
    async_processor = ImprovedAsyncProcessor(config)
    
    url = "https://example.com/cached_file.docx"
    
    print("\n첫 번째 요청 (캐시 없음):")
    time1, log1 = await async_processor.process_url_to_pdf_async(url, "사용자1")
    
    print("\n두 번째 요청 (캐시 있음):")
    time2, log2 = await async_processor.process_url_to_pdf_async(url, "사용자2")
    
    print(f"\n캐시 효과:")
    print(f"  첫 번째: {time1:.1f}초")
    print(f"  두 번째: {time2:.3f}초")
    if time1 > time2:
        improvement = ((time1 - time2) / time1) * 100
        print(f"  개선율: {improvement:.1f}%")

def cleanup_test_files(config: TestConfig):
    """테스트 파일 정리"""
    if config.temp_dir.exists():
        shutil.rmtree(config.temp_dir)
        print(f"\n🧹 테스트 파일 정리 완료")

async def main():
    """메인 테스트 실행"""
    print("🚀 현실적인 비동기 처리 성능 테스트")
    print("LibreOffice subprocess, 네트워크 다운로드, 파일 I/O 병목점 시뮬레이션")
    
    config = TestConfig()
    
    try:
        # 핵심 테스트: 동시 요청 처리
        await test_concurrent_requests()
        
        # 캐시 효과 테스트
        await test_cache_hit_scenario()
        
        print("\n" + "=" * 60)
        print("✅ 모든 테스트 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 테스트 중 오류: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cleanup_test_files(config)

if __name__ == "__main__":
    print("실행 중... (예상 소요시간: 30-60초)")
    asyncio.run(main())