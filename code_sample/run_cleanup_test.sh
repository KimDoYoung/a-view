#!/bin/bash

# test_cleanup_file.py 실행 스크립트
# A-View 캐시 정리 함수 테스트를 위한 편의 스크립트

set -e

# 프로젝트 루트로 이동
cd "$(dirname "$0")/.."

# Python 경로 확인 및 가상환경 활성화
if [ -d ".venv" ]; then
    echo "🐍 uv 가상환경 활성화 중..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    else
        echo "⚠️  가상환경 활성화 스크립트를 찾을 수 없습니다"
    fi
fi

# Python 경로 출력
echo "📍 Python: $(which python)"
echo "📍 작업 디렉토리: $(pwd)"
echo ""

# 스크립트 실행
if [ $# -eq 0 ]; then
    echo "🎯 캐시 정리 테스트 - 사용법"
    echo "=" * 40
    echo ""
    echo "📋 기본 사용법:"
    echo "  ./code_sample/run_cleanup_test.sh --help"
    echo ""
    echo "🔧 테스트 파일 생성 및 분석:"
    echo "  ./code_sample/run_cleanup_test.sh --create-test --verbose"
    echo ""
    echo "🧪 1시간 이상된 파일 시뮬레이션:"
    echo "  ./code_sample/run_cleanup_test.sh --hours 1 --dry-run"
    echo ""
    echo "🗑️  실제 캐시 정리 (24시간 기준):"
    echo "  ./code_sample/run_cleanup_test.sh --hours 24"
    echo ""
    echo "💡 모든 옵션 보기:"
    python code_sample/test_cleanup_file.py --help
else
    echo "🚀 캐시 정리 테스트 실행 중..."
    python code_sample/test_cleanup_file.py "$@"
fi