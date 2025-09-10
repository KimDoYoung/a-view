#!/bin/bash

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# 사용법 출력
usage() {
    cat << EOF
사용법: $0 [COMMAND] [ENVIRONMENT]

COMMANDS:
    build       이미지 빌드
    up          서비스 시작
    down        서비스 중지
    restart     서비스 재시작  
    logs        로그 보기
    status      서비스 상태 확인
    clean       사용하지 않는 이미지/볼륨 정리

ENVIRONMENTS:
    local       개발 환경 (Windows)
    test        테스트 환경 (Linux)
    real        운영 환경 (Linux)

예시:
    $0 up local          # 로컬 환경 시작
    $0 build test        # 테스트 환경 이미지 빌드
    $0 logs real -f      # 운영 환경 실시간 로그
    $0 restart test      # 테스트 환경 재시작
EOF
}

# 환경별 설정
get_compose_file() {
    case $1 in
        local)
            echo "docker-compose.local.yml"
            ;;
        test)
            echo "docker-compose.test.yml"
            ;;
        real)
            echo "docker-compose.real.yml"
            ;;
        *)
            error "지원하지 않는 환경: $1"
            usage
            exit 1
            ;;
    esac
}

# 환경별 전처리
prepare_environment() {
    local env=$1
    
    case $env in
        local)
            # Windows에서 Docker Desktop 실행 확인
            if ! docker info >/dev/null 2>&1; then
                error "Docker Desktop이 실행되지 않았습니다."
                exit 1
            fi
            # Windows 경로 생성
            mkdir -p /c/tmp/aview
            ;;
        test)
            # 테스트 서버 디렉토리 생성
            sudo mkdir -p /data1/aview/{data,logs}
            sudo chown -R aview:aview /data1/aview
            ;;
        real)
            # 운영 서버 디렉토리 생성
            sudo mkdir -p /opt/aview/{data,logs,ssl}
            sudo chown -R 1000:1000 /opt/aview
            
            # SSL 인증서 확인
            if [[ ! -f /opt/aview/ssl/cert.pem ]] || [[ ! -f /opt/aview/ssl/key.pem ]]; then
                warn "SSL 인증서가 없습니다. /opt/aview/ssl/ 에 cert.pem, key.pem 파일을 배치하세요."
            fi
            ;;
    esac
}

# Docker Compose 실행
run_compose() {
    local env=$1
    local command=$2
    shift 2
    local compose_file=$(get_compose_file $env)
    
    log "실행 중: docker compose -f $compose_file $command $@"
    docker compose -f $compose_file $command "$@"
}

# 메인 로직
main() {
    if [[ $# -lt 2 ]]; then
        usage
        exit 1
    fi

    local command=$1
    local env=$2
    shift 2

    # 환경 파일 존재 확인
    local env_file=".env.$env"
    if [[ ! -f $env_file ]]; then
        error "환경 파일이 없습니다: $env_file"
        exit 1
    fi

    case $command in
        build)
            log "[$env] 이미지 빌드 시작"
            prepare_environment $env
            run_compose $env build --no-cache
            log "[$env] 이미지 빌드 완료"
            ;;
        up)
            log "[$env] 서비스 시작"
            prepare_environment $env
            run_compose $env up -d
            log "[$env] 서비스 시작 완료"
            ;;
        down)
            log "[$env] 서비스 중지"
            run_compose $env down
            log "[$env] 서비스 중지 완료"
            ;;
        restart)
            log "[$env] 서비스 재시작"
            run_compose $env restart
            log "[$env] 서비스 재시작 완료"
            ;;
        logs)
            info "[$env] 로그 보기"
            run_compose $env logs "$@"
            ;;
        status)
            info "[$env] 서비스 상태"
            run_compose $env ps
            ;;
        clean)
            warn "[$env] 정리 작업 시작"
            docker system prune -f
            docker volume prune -f
            log "[$env] 정리 작업 완료"
            ;;
        *)
            error "지원하지 않는 명령어: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"