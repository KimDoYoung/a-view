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
사용법: $0 [COMMAND] [ENVIRONMENT] [OPTIONS]

COMMANDS:
    build       이미지 빌드
    up          서비스 시작
    down        서비스 중지
    restart     서비스 재시작  
    logs        로그 보기
    status      서비스 상태 확인
    clean       사용하지 않는 이미지/볼륨 정리
    clean-all   aview 관련 모든 컨테이너/이미지/볼륨 완전 삭제

ENVIRONMENTS:
    local       개발 환경 (Windows)
    test        테스트 환경 (Linux)
    real        운영 환경 (Linux)

OPTIONS:
    --no-cache          빌드 시 캐시 사용 안함
    --force-recreate    컨테이너 강제 재생성
    --dry-run          실제 실행하지 않고 명령어만 출력

예시:
    $0 up local                    # 로컬 환경 시작
    $0 build test --no-cache       # 테스트 환경 이미지 빌드 (캐시 없이)
    $0 up local --force-recreate   # 로컬 환경 시작 (강제 재생성)
    $0 logs real -f                # 운영 환경 실시간 로그
    $0 restart test                # 테스트 환경 재시작
    $0 build local --dry-run       # 명령어만 출력 (실행 안함)
    $0 clean-all local             # aview 관련 모든 리소스 삭제
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

# aview 관련 모든 리소스 정리
clean_all_aview() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    
    warn "[$env] aview 관련 모든 리소스를 삭제합니다."
    warn "이 작업은 되돌릴 수 없습니다. 5초 후 시작됩니다..."
    sleep 5
    
    # 컨테이너 중지 및 삭제
    info "컨테이너 중지 및 삭제..."
    if docker compose -f $compose_file ps -q 2>/dev/null | grep -q .; then
        docker compose -f $compose_file down -v --remove-orphans
    fi
    
    # aview 관련 컨테이너 강제 삭제
    info "aview 관련 컨테이너 강제 삭제..."
    local aview_containers=$(docker ps -aq --filter "name=aview" 2>/dev/null || true)
    if [[ -n "$aview_containers" ]]; then
        docker rm -f $aview_containers
    fi
    
    # aview 관련 이미지 삭제
    info "aview 관련 이미지 삭제..."
    local aview_images=$(docker images --filter "reference=*aview*" -q 2>/dev/null || true)
    if [[ -n "$aview_images" ]]; then
        docker rmi -f $aview_images
    fi
    
    # aview 관련 볼륨 삭제
    info "aview 관련 볼륨 삭제..."
    local aview_volumes=$(docker volume ls --filter "name=aview" -q 2>/dev/null || true)
    if [[ -n "$aview_volumes" ]]; then
        docker volume rm -f $aview_volumes
    fi
    
    # aview 관련 네트워크 삭제
    info "aview 관련 네트워크 삭제..."
    local aview_networks=$(docker network ls --filter "name=aview" -q 2>/dev/null || true)
    if [[ -n "$aview_networks" ]]; then
        docker network rm $aview_networks 2>/dev/null || true
    fi
    
    # 데이터 디렉토리 정리 (선택적)
    read -p "데이터 디렉토리도 삭제하시겠습니까? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        case $env in
            local)
                warn "로컬 임시 디렉토리 삭제..."
                rm -rf /c/tmp/aview
                ;;
            test)
                warn "테스트 데이터 디렉토리 삭제..."
                sudo rm -rf /data1/aview
                ;;
            real)
                warn "운영 데이터 디렉토리 삭제..."
                sudo rm -rf /opt/aview
                ;;
        esac
    fi
    
    log "[$env] aview 관련 모든 리소스 삭제 완료"
}

# Docker Compose 실행
run_compose() {
    local env=$1
    local command=$2
    local dry_run=$3
    shift 3
    local compose_file=$(get_compose_file $env)
    local full_command="docker compose -f $compose_file $command $@"
    
    info "실행할 명령어: $full_command"
    
    if [[ $dry_run == "true" ]]; then
        warn "[DRY RUN] 실제로는 실행되지 않습니다."
        return 0
    fi
    
    log "실행 중: $full_command"
    docker compose -f $compose_file $command "$@"
}

# 옵션 파싱
parse_options() {
    local -n options_ref=$1
    shift
    
    options_ref[no_cache]=false
    options_ref[force_recreate]=false
    options_ref[dry_run]=false
    options_ref[extra_args]=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-cache)
                options_ref[no_cache]=true
                shift
                ;;
            --force-recreate)
                options_ref[force_recreate]=true
                shift
                ;;
            --dry-run)
                options_ref[dry_run]=true
                shift
                ;;
            -*)
                # 다른 docker compose 옵션들 (예: -f, --follow 등)
                options_ref[extra_args]+="$1 "
                shift
                ;;
            *)
                options_ref[extra_args]+="$1 "
                shift
                ;;
        esac
    done
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

    # 옵션 파싱
    declare -A options
    parse_options options "$@"

    # 환경 파일 존재 확인
    local env_file=".env.$env"
    if [[ ! -f $env_file ]]; then
        error "환경 파일이 없습니다: $env_file"
        exit 1
    fi

    case $command in
        build)
            log "[$env] 이미지 빌드 시작"
            if [[ ${options[dry_run]} != "true" ]]; then
                prepare_environment $env
            fi
            
            local build_args=""
            if [[ ${options[no_cache]} == "true" ]]; then
                build_args+="--no-cache "
            fi
            build_args+=${options[extra_args]}
            
            run_compose $env "build" ${options[dry_run]} $build_args
            
            if [[ ${options[dry_run]} != "true" ]]; then
                log "[$env] 이미지 빌드 완료"
            fi
            ;;
        up)
            log "[$env] 서비스 시작"
            if [[ ${options[dry_run]} != "true" ]]; then
                prepare_environment $env
            fi
            
            local up_args="-d "
            if [[ ${options[force_recreate]} == "true" ]]; then
                up_args+="--force-recreate "
            fi
            up_args+=${options[extra_args]}
            
            run_compose $env "up" ${options[dry_run]} $up_args
            
            if [[ ${options[dry_run]} != "true" ]]; then
                log "[$env] 서비스 시작 완료"
            fi
            ;;
        down)
            log "[$env] 서비스 중지"
            run_compose $env "down" ${options[dry_run]} ${options[extra_args]}
            if [[ ${options[dry_run]} != "true" ]]; then
                log "[$env] 서비스 중지 완료"
            fi
            ;;
        restart)
            log "[$env] 서비스 재시작"
            run_compose $env "restart" ${options[dry_run]} ${options[extra_args]}
            if [[ ${options[dry_run]} != "true" ]]; then
                log "[$env] 서비스 재시작 완료"
            fi
            ;;
        logs)
            info "[$env] 로그 보기"
            run_compose $env "logs" ${options[dry_run]} ${options[extra_args]}
            ;;
        status)
            info "[$env] 서비스 상태"
            run_compose $env "ps" ${options[dry_run]} ${options[extra_args]}
            ;;
        clean)
            warn "[$env] 정리 작업 시작"
            if [[ ${options[dry_run]} == "true" ]]; then
                info "[DRY RUN] docker system prune -f"
                info "[DRY RUN] docker volume prune -f"
            else
                docker system prune -f
                docker volume prune -f
                log "[$env] 정리 작업 완료"
            fi
            ;;
        clean-all)
            if [[ ${options[dry_run]} == "true" ]]; then
                warn "[DRY RUN] aview 관련 모든 리소스 삭제 명령들을 출력합니다:"
                info "[DRY RUN] docker compose -f $(get_compose_file $env) down -v --remove-orphans"
                info "[DRY RUN] docker rm -f \$(docker ps -aq --filter 'name=aview' --filter 'name=a-view')"
                info "[DRY RUN] docker rmi -f \$(docker images --filter 'reference=*aview*' --filter 'reference=*a-view*' -q)"
                info "[DRY RUN] docker volume rm -f \$(docker volume ls --filter 'name=aview' --filter 'name=a-view' -q)"
                info "[DRY RUN] docker network rm \$(docker network ls --filter 'name=aview' --filter 'name=a-view' -q)"

            else
                clean_all_aview $env
            fi
            ;;
        *)
            error "지원하지 않는 명령어: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"