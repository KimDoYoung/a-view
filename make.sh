#!/bin/bash

# A-View 실행파일 빌드 스크립트
# 사용법: ./make.sh [옵션]
# 옵션:
#   package   - 패키지 형태로 빌드 (기본값)
#   binary    - PyInstaller로 단일 실행파일 생성
#   clean     - 빌드 파일 정리
#   run       - 개발 서버 실행
#   test      - 테스트 실행

set -e  # 에러 발생시 즉시 종료

# 리눅스 환경 체크
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "❌ 이 스크립트는 Linux 환경에서만 실행할 수 있습니다."
    echo "현재 OS: $OSTYPE"
    echo "💡 Linux 서버에서 실행해주세요."
    exit 1
fi

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# uv 가상환경 활성화 확인
check_uv_env() {
    if [ ! -d ".venv" ]; then
        log_error "uv 가상환경(.venv)이 없습니다. 'uv sync'를 먼저 실행하세요."
        exit 1
    fi
    
    log_info "uv 가상환경 활성화 중..."
    source .venv/bin/activate
    
    # Python 경로 확인
    PYTHON_PATH=$(which python)
    log_info "Python 경로: $PYTHON_PATH"
}

# PyInstaller 설치 확인
install_pyinstaller() {
    if ! python -c "import PyInstaller" 2>/dev/null; then
        log_info "PyInstaller 설치 중..."
        uv add pyinstaller --dev
    fi
}

# 단일 실행파일 생성
build_binary() {
    log_info "=== 단일 실행파일 빌드 시작 ==="
    
    check_uv_env
    install_pyinstaller
    
    # 빌드 디렉토리 정리
    rm -rf build/ dist/ *.spec
    
    # PyInstaller 명령어 실행
    log_info "PyInstaller로 실행파일 생성 중..."
    
    pyinstaller \
        --onefile \
        --name aview \
        --add-data "app/templates:app/templates" \
        --add-data "app/static:app/static" \
        --hidden-import uvicorn.lifespan.on \
        --hidden-import uvicorn.loops.auto \
        --hidden-import uvicorn.protocols.websockets.auto \
        --collect-all fastapi \
        --collect-all jinja2 \
        --collect-all pydantic \
        app/main.py
    
    if [ -f "dist/aview" ]; then
        log_success "실행파일 생성 완료: dist/aview"
        log_info "실행 방법: ./dist/aview"
        
        # 실행 권한 부여
        chmod +x dist/aview
        
        # 파일 크기 확인
        FILE_SIZE=$(du -h dist/aview | cut -f1)
        log_info "실행파일 크기: $FILE_SIZE"
    else
        log_error "실행파일 생성 실패"
        exit 1
    fi
}

# 패키지 형태 빌드
build_package() {
    log_info "=== 패키지 형태 빌드 시작 ==="
    
    check_uv_env
    install_pyinstaller
    
    # 빌드 디렉토리 정리
    rm -rf build/ dist/ *.spec
    
    # 패키지 형태로 빌드
    pyinstaller \
        --name aview \
        --add-data "app/templates:app/templates" \
        --add-data "app/static:app/static" \
        --hidden-import uvicorn.lifespan.on \
        --hidden-import uvicorn.loops.auto \
        --hidden-import uvicorn.protocols.websockets.auto \
        --collect-all fastapi \
        --collect-all jinja2 \
        --collect-all pydantic \
        app/main.py
    
    if [ -d "dist/aview" ]; then
        log_success "패키지 빌드 완료: dist/aview/"
        log_info "실행 방법: ./dist/aview/aview"
        
        # 실행 권한 부여
        chmod +x dist/aview/aview
    else
        log_error "패키지 빌드 실패"
        exit 1
    fi
}

# 개발 서버 실행
run_dev() {
    log_info "=== 개발 서버 실행 ==="
    
    check_uv_env
    
    # 환경 설정 확인
    if [ ! -f ".env.local" ]; then
        log_warning ".env.local 파일이 없습니다. .env.sample을 복사하세요."
    fi
    
    # 개발 서버 실행
    log_info "FastAPI 개발 서버 시작 중..."
    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8003
}

# 테스트 실행
run_test() {
    log_info "=== 테스트 실행 ==="
    
    check_uv_env
    
    # 테스트 도구 설치 확인
    if ! python -c "import pytest" 2>/dev/null; then
        log_info "pytest 설치 중..."
        uv add pytest --dev
    fi
    
    # 테스트 실행
    python -m pytest tests/ -v
}

# 빌드 파일 정리
clean() {
    log_info "=== 빌드 파일 정리 ==="
    
    rm -rf build/
    rm -rf dist/
    rm -rf __pycache__/
    rm -rf app/__pycache__/
    rm -rf app/*/__pycache__/
    rm -f *.spec
    
    log_success "정리 완료"
}

# 도움말 표시
show_help() {
    echo "A-View 빌드 스크립트"
    echo ""
    echo "사용법: ./make.sh [옵션]"
    echo ""
    echo "옵션:"
    echo "  binary     PyInstaller로 단일 실행파일 생성"
    echo "  package    PyInstaller로 패키지 형태 빌드"
    echo "  run        개발 서버 실행"
    echo "  test       테스트 실행"
    echo "  clean      빌드 파일 정리"
    echo "  help       이 도움말 표시"
    echo ""
    echo "예시:"
    echo "  ./make.sh binary    # 단일 실행파일 생성"
    echo "  ./make.sh run       # 개발 서버 실행"
    echo "  ./make.sh clean     # 빌드 파일 정리"
}

# 메인 로직
case "${1:-help}" in
    "binary")
        build_binary
        ;;
    "package")
        build_package
        ;;
    "run")
        run_dev
        ;;
    "test")
        run_test
        ;;
    "clean")
        clean
        ;;
    "help"|*)
        show_help
        ;;
esac