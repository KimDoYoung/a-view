#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import argparse
import csv
import statistics
import random
from datetime import datetime
from collections import defaultdict

class StressTest:
    def __init__(self, base_url="http://localhost:8003", concurrent_users=10, total_requests=100, duration=None):
        self.base_url = base_url
        self.concurrent_users = concurrent_users
        self.total_requests = total_requests
        self.duration = duration
        self.results = []
        
        # 테스트할 API 엔드포인트들
        self.apis = [
            "/convert?path=c:/tmp/aview//11.docx&output=pdf",
            "/convert?path=c:/tmp/aview/files/22.xlsx&output=html", 
            "/convert?url=http://localhost:8003/aview/files/11.docx&output=pdf",
            "/convert?url=http://localhost:8003/aview/files/11.docx&output=html",
            "/view?path=c:/tmp/aview/files/33.pptx",
            "/view?url=http://localhost:8003/aview/files/11.docx"
        ]
    
    async def single_request(self, session, req_id):
        """단일 HTTP 요청 실행"""
        api_endpoint = random.choice(self.apis)
        url = f"{self.base_url}{api_endpoint}"
        
        start_time = time.time()
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)  # 30초 타임아웃
            async with session.get(url, timeout=timeout) as response:
                await response.text()  # 응답 내용 읽기
                
                end_time = time.time()
                response_time = end_time - start_time
                
                result = {
                    'req_id': req_id,
                    'api': api_endpoint,
                    'status': response.status,
                    'response_time': response_time,
                    'timestamp': datetime.now().isoformat(),
                    'success': 200 <= response.status < 400
                }
                
                self.results.append(result)
                
                if req_id % 10 == 0:  # 진행 상황 출력
                    print(f"Completed: {req_id} requests")
                    
        except asyncio.TimeoutError:
            end_time = time.time()
            result = {
                'req_id': req_id,
                'api': api_endpoint,
                'status': 'TIMEOUT',
                'response_time': end_time - start_time,
                'timestamp': datetime.now().isoformat(),
                'success': False
            }
            self.results.append(result)
            
        except Exception as e:
            end_time = time.time()
            result = {
                'req_id': req_id,
                'api': api_endpoint,
                'status': f'ERROR: {str(e)}',
                'response_time': end_time - start_time,
                'timestamp': datetime.now().isoformat(),
                'success': False
            }
            self.results.append(result)
    
    async def run_by_count(self):
        """요청 수 기반 테스트"""
        connector = aiohttp.TCPConnector(limit=self.concurrent_users * 2)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            semaphore = asyncio.Semaphore(self.concurrent_users)
            
            async def bounded_request(req_id):
                async with semaphore:
                    await self.single_request(session, req_id)
            
            tasks = [bounded_request(i) for i in range(1, self.total_requests + 1)]
            await asyncio.gather(*tasks)
    
    async def run_by_duration(self):
        """시간 기반 테스트"""
        connector = aiohttp.TCPConnector(limit=self.concurrent_users * 2)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            semaphore = asyncio.Semaphore(self.concurrent_users)
            req_counter = 0
            end_time = time.time() + self.duration
            
            async def bounded_request():
                nonlocal req_counter
                req_counter += 1
                async with semaphore:
                    await self.single_request(session, req_counter)
            
            tasks = []
            while time.time() < end_time:
                if len(tasks) < self.concurrent_users * 2:  # 큐 크기 제한
                    task = asyncio.create_task(bounded_request())
                    tasks.append(task)
                    await asyncio.sleep(0.01)  # CPU 과부하 방지
                
                # 완료된 태스크 정리
                tasks = [t for t in tasks if not t.done()]
            
            # 남은 태스크 완료 대기
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run_test(self):
        """스트레스 테스트 실행"""
        print(f"=== Stress Test Configuration ===")
        print(f"Base URL: {self.base_url}")
        print(f"Concurrent Users: {self.concurrent_users}")
        
        if self.duration:
            print(f"Duration: {self.duration} seconds")
        else:
            print(f"Total Requests: {self.total_requests}")
        
        print(f"API Endpoints: {len(self.apis)}")
        print("=" * 40)
        
        start_total = time.time()
        
        if self.duration:
            await self.run_by_duration()
        else:
            await self.run_by_count()
            
        end_total = time.time()
        total_time = end_total - start_total
        
        self.analyze_results(total_time)
    
    def analyze_results(self, total_time):
        """결과 분석 및 출력"""
        if not self.results:
            print("No results to analyze!")
            return
        
        # CSV 파일로 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = f"stress_results_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys())
            writer.writeheader()
            writer.writerows(self.results)
        
        # 통계 계산
        successful_requests = [r for r in self.results if r['success']]
        response_times = [r['response_time'] for r in successful_requests]
        
        status_counts = defaultdict(int)
        api_counts = defaultdict(int)
        
        for result in self.results:
            status_counts[str(result['status'])] += 1
            api_counts[result['api']] += 1
        
        # 결과 출력
        print(f"\n=== Test Results ===")
        print(f"Total execution time: {total_time:.2f} seconds")
        print(f"Total requests: {len(self.results)}")
        print(f"Successful requests: {len(successful_requests)}")
        print(f"Failed requests: {len(self.results) - len(successful_requests)}")
        print(f"Requests per second: {len(self.results) / total_time:.2f}")
        print(f"Results saved to: {csv_file}")
        
        if response_times:
            print(f"\n=== Response Time Statistics (seconds) ===")
            print(f"Average: {statistics.mean(response_times):.3f}")
            print(f"Median: {statistics.median(response_times):.3f}")
            print(f"Min: {min(response_times):.3f}")
            print(f"Max: {max(response_times):.3f}")
            print(f"95th percentile: {sorted(response_times)[int(len(response_times) * 0.95)]:.3f}")
        
        print(f"\n=== Status Code Distribution ===")
        for status, count in sorted(status_counts.items()):
            percentage = (count / len(self.results)) * 100
            print(f"{status}: {count} ({percentage:.1f}%)")
        
        print(f"\n=== API Endpoint Distribution ===")
        for api, count in sorted(api_counts.items()):
            percentage = (count / len(self.results)) * 100
            print(f"{api}: {count} ({percentage:.1f}%)")

async def main():
    parser = argparse.ArgumentParser(description="FastAPI Stress Test Tool")
    parser.add_argument("--url", default="http://localhost:8003", help="Base URL (default: http://localhost:8003)")
    parser.add_argument("--concurrent", "-c", type=int, default=10, help="Concurrent users (default: 10)")
    parser.add_argument("--requests", "-n", type=int, help="Total number of requests")
    parser.add_argument("--duration", "-d", type=int, help="Test duration in seconds")
    
    args = parser.parse_args()
    
    if not args.requests and not args.duration:
        args.requests = 100  # 기본값
    
    if args.requests and args.duration:
        print("Error: Cannot specify both --requests and --duration")
        return
    
    stress_test = StressTest(
        base_url=args.url,
        concurrent_users=args.concurrent,
        total_requests=args.requests,
        duration=args.duration
    )
    
    await stress_test.run_test()

if __name__ == "__main__":
    asyncio.run(main())