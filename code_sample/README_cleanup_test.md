# 캐시 정리 함수 테스트

`cleanup_old_cache_files` 함수를 테스트하기 위한 스크립트입니다.

## 파일 구조

- `test_cleanup_file.py` - 메인 테스트 스크립트
- `run_cleanup_test.sh` - 실행 편의 스크립트  
- `README_cleanup_test.md` - 이 문서

## 사용법

### 1. 기본 사용법

```bash
# 도움말 보기
python code_sample/test_cleanup_file.py --help

# 또는 편의 스크립트 사용
./code_sample/run_cleanup_test.sh --help
```

### 2. 테스트 파일 생성 및 분석

```bash
# 테스트용 더미 파일들 생성하고 상세 분석
python code_sample/test_cleanup_file.py --create-test --verbose

# 또는
./code_sample/run_cleanup_test.sh --create-test --verbose
```

### 3. 시뮬레이션 (DRY RUN)

```bash
# 1시간 이상된 파일들 삭제 시뮬레이션
python code_sample/test_cleanup_file.py --hours 1 --dry-run

# 24시간 이상된 파일들 삭제 시뮬레이션  
python code_sample/test_cleanup_file.py --hours 24 --dry-run
```

### 4. 실제 캐시 정리

```bash
# 24시간 이상된 파일들 실제 삭제
python code_sample/test_cleanup_file.py --hours 24

# 1시간 이상된 파일들 실제 삭제 (테스트용)
python code_sample/test_cleanup_file.py --hours 1
```

## 옵션 설명

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--hours N` | N시간 이상된 파일 삭제 | 24 |
| `--dry-run` | 실제 삭제하지 않고 시뮬레이션만 실행 | False |
| `--create-test` | 테스트용 더미 파일들 생성 | False |
| `--verbose` | 상세 로그 출력 | False |
| `--help` | 도움말 표시 | - |

## 테스트 시나리오

스크립트는 다음과 같은 테스트 파일들을 생성합니다:

- **very_old**: 48시간 전 파일들 (삭제 대상)
- **old**: 25시간 전 파일들 (삭제 대상)  
- **recent**: 12시간 전 파일들 (유지 대상)
- **new**: 1시간 전 파일들 (유지 대상)
- **very_new**: 6분 전 파일들 (유지 대상)

## 출력 예시

### 테스트 파일 생성 및 분석

```
🔧 테스트용 더미 파일 생성 중...
✅ 20개의 테스트 파일 생성 완료

📊 파일 분석 (기준: 24시간)
============================================================

📁 캐시 디렉토리: /tmp/aview/cache
  test_very_old_0_cache.txt        48.0시간       45B 🗑️  삭제 대상
  test_old_0_cache.txt             25.0시간       42B 🗑️  삭제 대상
  test_recent_0_cache.txt          12.0시간       44B ✅ 유지
  test_new_0_cache.txt              1.0시간       41B ✅ 유지
```

### DRY RUN 결과

```
🧹 캐시 정리 시작 (DRY RUN)
==================================================
📁 캐시 디렉토리 정리: /tmp/aview/cache
  [DRY] 삭제 예정: test_very_old_0_cache.txt (48.0시간 전)
  [DRY] 삭제 예정: test_old_0_cache.txt (25.0시간 전)

📋 정리 결과
==============================
삭제 예정: 10개 파일
총 크기:   450B (0.4KB)
실패:     0개 파일
```

### 실제 실행 결과

```
🧹 캐시 정리 시작 (REAL RUN)
==================================================
📁 캐시 디렉토리 정리: /tmp/aview/cache
  ✅ 삭제 완료: test_very_old_0_cache.txt (48.0시간 전)
  ✅ 삭제 완료: test_old_0_cache.txt (25.0시간 전)

📋 정리 결과
==============================
삭제 완료: 10개 파일
총 크기:   450B (0.4KB)
실패:     0개 파일

🎯 최종 결과
==============================
✅ 캐시 정리 완료 - 10개 파일을 삭제했습니다.
```

## 주의사항

- `--create-test` 옵션은 실제 캐시 디렉토리에 테스트 파일을 생성합니다
- 실제 운영 환경에서는 `--dry-run`으로 먼저 확인해보세요
- 테스트 후에는 `--hours 0 --dry-run`으로 모든 파일을 확인할 수 있습니다

## 실행 권한 설정

```bash
# 스크립트에 실행 권한 부여
chmod +x code_sample/test_cleanup_file.py
chmod +x code_sample/run_cleanup_test.sh
```
