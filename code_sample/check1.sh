#!/bin/bash

echo "========================================="
echo "A-View API Test Script"
echo "========================================="
start_time=$(date +%s)

BASE_URL="http://localhost:8003"
SAMPLE_PATH="c:/tmp/aview/files"

# 색깔 출력을 위한 함수
print_section() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
}

print_step() {
    echo ""
    echo "--- $1 ---"
}

# 서버 연결 확인 함수
check_server_connection() {
    local base_url="$1"
    
    echo "서버 연결 확인 중: $base_url"
    
    # curl로 서버 응답 확인 (타임아웃 5초)
    if curl -s -f --connect-timeout 5 --max-time 10 "$base_url" > /dev/null 2>&1; then
        echo "OK: 서버가 정상적으로 응답합니다."
        return 0
    else
        echo "ERROR: 서버에 연결할 수 없습니다."
        echo "다음을 확인해주세요:"
        echo "  1. 서버가 실행 중인지 확인"
        echo "  2. 포트 8003이 사용 가능한지 확인" 
        echo "  3. 방화벽 설정 확인"
        echo "  4. URL이 올바른지 확인: $base_url"
        return 1
    fi
}

# 파일 존재 여부 확인 함수
check_file_exists() {
    local file_path="$1"
    local file_name="$2"
    
    if [ ! -f "$file_path" ]; then
        echo "ERROR: 파일이 존재하지 않습니다 - $file_name"
        echo "경로: $file_path"
        return 1
    fi
    return 0
}

# URL 인코딩 함수 (한글 처리)
url_encode() {
    local string="$1"
    # Python을 사용하여 URL 인코딩 (한글 지원)
    python3 -c "import urllib.parse; print(urllib.parse.quote('$string'))" 2>/dev/null || \
    python -c "import urllib; print urllib.quote('$string')" 2>/dev/null || \
    echo "$string"  # Python이 없으면 원본 반환
}

# Convert API 호출 함수 (한글 파일명 지원)
call_convert_api() {
    local arg1="$1"
    local arg2="$2"
    local arg3="$3"
    local url=""
    local description=""
    
    # 인자 개수에 따른 처리
    if [[ "$arg1" == http* ]]; then
        # URL로 시작하는 경우: call_api "${BASE_URL}/aview/files/${file}" "url" "pdf"
        local base_url="$arg1"
        local param_type="$arg2"  # "url" or "path"
        local output_format="$arg3"  # "pdf" or "html"
        
        if [[ "$param_type" == "url" ]]; then
            # URL 파라미터 사용
            url="${BASE_URL}/convert?url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$base_url'))" 2>/dev/null || echo "$base_url")&output=$output_format"
            description="Convert via URL to $output_format"
        elif [[ "$param_type" == "path" ]]; then
            # Path 파라미터 사용
            url="${BASE_URL}/convert?path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$base_url'))" 2>/dev/null || echo "$base_url")&output=$output_format"
            description="Convert via PATH to $output_format"
        else
            # 일반 URL 호출
            url="$arg1"
            description="${arg2:-API 호출}"
        fi
    else
        # 파일명으로 시작하는 경우: call_api "${file}" "path" "pdf"
        local filename="$arg1"
        local param_type="$arg2"  # "path" or "url"
        local output_format="$arg3"  # "pdf" or "html"
        
        if [[ "$param_type" == "path" ]]; then
            # Path 파라미터 사용
            local full_path="${SAMPLE_PATH}/${filename}"
            url="${BASE_URL}/convert?path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$full_path'))" 2>/dev/null || echo "$full_path")&output=$output_format"
            description="$filename → $output_format (path)"
        elif [[ "$param_type" == "url" ]]; then
            # URL 파라미터 사용
            local file_url="${BASE_URL}/aview/files/${filename}"
            url="${BASE_URL}/convert?url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$file_url'))" 2>/dev/null || echo "$file_url")&output=$output_format"
            description="$filename → $output_format (url)"
        else
            # 기본 URL 호출 (2개 인자만 있는 경우)
            if [[ "$arg1" == *"?"* ]]; then
                # 이미 완성된 URL
                url="$arg1"
                description="${arg2:-API 호출}"
            else
                # View API 등 다른 경우
                url="$arg1"
                description="${arg2:-API 호출}"
            fi
        fi
    fi
    
    echo "[$description]"
    echo "Request URL: $url"
    
    # curl 실행
    local response
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
    
    # 응답 파싱
    local http_code time_total body
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -2)
    
    echo "HTTP Code: $http_code"
    echo "Response Time: ${time_total}s"
    
    # 응답 본문 출력 (HTML인 경우 처음 100자만)
    if [[ "$body" == *"<html"* ]] || [[ "$body" == *"<!DOCTYPE"* ]]; then
        echo "Response: [HTML Content - ${#body} bytes]"
        echo "Preview: ${body:0:100}..."
    else
        echo "Response: $body"
    fi
    
    echo ""
    # HTTP 상태 코드 확인
    if [[ "$http_code" != "200" ]]; then
        echo "❌========================================="
        echo "ERROR: API 호출 실패 (HTTP $http_code)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        echo "❌========================================="
        echo "테스트 중단됨"
        exit 1
    fi
    # 사용자 확인 대기
    # read -r -p "계속하려면 Enter (Ctrl+C로 종료)..." _
}

# Python이 없는 경우를 위한 대체 URL 인코딩 함수
url_encode_fallback() {
    local string="$1"
    local strlen=${#string}
    local encoded=""
    local pos c o
    
    for (( pos=0 ; pos<strlen ; pos++ )); do
        c=${string:$pos:1}
        case "$c" in
            [-_.~a-zA-Z0-9] ) o="${c}" ;;
            * ) printf -v o '%%%02X' "'$c" ;;
        esac
        encoded+="${o}"
    done
    echo "${encoded}"
}

# Python 존재 여부 확인 및 URL 인코딩 래퍼
safe_url_encode() {
    local string="$1"
    
    # Python3 시도
    if command -v python3 &> /dev/null; then
        python3 -c "import urllib.parse; print(urllib.parse.quote('$string'))" 2>/dev/null && return
    fi
    
    # Python2 시도
    if command -v python &> /dev/null; then
        python -c "import urllib; print urllib.quote('$string')" 2>/dev/null && return
    fi
    
    # 대체 함수 사용
    url_encode_fallback "$string"
}

# Cache 상태 확인 함수
cache_stats() {
    cache_stats_response=$(curl -s -w "\n%{http_code}\n%{time_total}" "${BASE_URL}/cache/stats")
    cache_stats_http_code=$(echo "$cache_stats_response" | tail -n 2 | head -n 1)
    cache_stats_time=$(echo "$cache_stats_response" | tail -n 1)
    cache_stats_body=$(echo "$cache_stats_response" | head -n -2)

    echo "HTTP Code: $cache_stats_http_code"
    echo "Response Time: ${cache_stats_time}s"
    echo "Response: $cache_stats_body"

    # JSON 응답을 파일로 저장
    if [[ "$cache_stats_http_code" == "200" && -n "$cache_stats_body" ]]; then
        cache_stats_file="cache_stats_$(date +%Y%m%d_%H%M%S).json"
        echo "$cache_stats_body" > "$cache_stats_file"
        echo "Cache stats saved to: $cache_stats_file"
    fi
}

# View API 호출 함수
call_view_api() {
    local filename="$1"
    local param_type="$2"  # "path" or "url"
    local url=""
    local description=""
    
    if [[ "$param_type" == "path" ]]; then
        # Path 파라미터 사용
        local full_path="${SAMPLE_PATH}/${filename}"
        local encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$full_path'))" 2>/dev/null || echo "$full_path")
        url="${BASE_URL}/view?path=${encoded_path}"
        description="$filename → View (path)"
    elif [[ "$param_type" == "url" ]]; then
        # URL 파라미터 사용
        local file_url="${BASE_URL}/aview/files/${filename}"
        local encoded_url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$file_url'))" 2>/dev/null || echo "$file_url")
        url="${BASE_URL}/view?url=${encoded_url}"
        description="$filename → View (url)"
    fi
    
    echo "[$description]"
    echo "Request URL: $url"
    
    # curl 실행
    local response
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
    
    # 응답 파싱
    local http_code time_total body
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -2)
    
    echo "HTTP Code: $http_code"
    echo "Response Time: ${time_total}s"
    
    # 응답 본문 출력 (HTML인 경우 처음 100자만)
    if [[ "$body" == *"<html"* ]] || [[ "$body" == *"<!DOCTYPE"* ]]; then
        echo "Response: [HTML Content - ${#body} bytes]"
        echo "Preview: ${body:0:100}..."
    else
        echo "Response: $body"
    fi
    
    echo ""
    # HTTP 상태 코드 확인
    if [[ "$http_code" != "200" ]]; then
        echo "❌========================================="
        echo "ERROR: View API 호출 실패 (HTTP $http_code)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        echo "❌========================================="
        echo "테스트 중단됨"
        exit 1
    fi
}

# 서버 연결 상태 확인
print_section "0. 서버 연결 상태 확인"
if ! check_server_connection "$BASE_URL"; then
    echo ""
    echo "========================================="
    echo "ERROR: A-View 서버에 연결할 수 없습니다."
    echo "========================================="
    echo "서버를 시작한 후 다시 실행해주세요."
    exit 1
fi
echo "✅ 서버연결상태 확인"

# read -r -p "계속하려면 Enter (Ctrl+C로 종료)..." _
# 필수 파일들 존재 여부 확인
print_section "1. 필수 파일 존재 여부 확인"
echo "샘플 파일 경로: $SAMPLE_PATH"

required_files=(
    "1.jpg"
    "1.csv"
    "1.txt"
    "1.md"
    "1.png"
    "1.pdf"
)
office_files=(
    "1.docx"
    "2.pptx"
    "3.xlsx"
    # "테스트abc123.docx"
    # "테스트abc123.xlsx" 
    # "테스트abc123.pptx"
)
view_files=(
    "${required_files[@]}"
    "${office_files[@]}"
)
missing_files=()

for file in "${required_files[@]}"; do
    file_path="${SAMPLE_PATH}/${file}"
    if ! check_file_exists "$file_path" "$file"; then
        missing_files+=("$file")
    else
        echo "OK: $file"
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    echo ""
    echo "========================================="
    echo "ERROR: 다음 파일들이 누락되었습니다:"
    for file in "${missing_files[@]}"; do
        echo "  - $file"
    done
    echo "========================================="
    echo "모든 필수 파일이 존재하는지 확인 후 다시 실행해주세요."
    echo "필요한 파일들을 $SAMPLE_PATH 폴더에 준비해주세요."
    exit 1
fi

echo "✅ 모든 필수 파일이 확인되었습니다."

print_section "2. Cache 초기화"
echo "Cache 초기화 중..."
cache_response=$(curl -X POST -s -w "\n%{http_code}\n%{time_total}" "${BASE_URL}/cache/clear-all?confirm=true")
cache_http_code=$(echo "$cache_response" | tail -n 2 | head -n 1)
cache_time=$(echo "$cache_response" | tail -n 1)
cache_body=$(echo "$cache_response" | head -n -2)
echo "HTTP Code: $cache_http_code"
echo "Response Time: ${cache_time}s"
echo "Response: $cache_body"
echo ""
# Cache 상태 확인
print_step "Cache 상태 확인"
cache_stats
echo "✅ Cache 초기화 및 상태 확인 완료"

print_section "3. Office 문서 Convert 테스트 (path 파라미터)"
print_step "Office convert to PDF/HTML"
for file in "${office_files[@]}"; do
    print_step "$file to PDF/HTML (path & url)"
    
    # Path parameter tests
    call_convert_api "${file}" "path" "pdf"
    call_convert_api "${file}" "path" "html"

    # URL parameter tests
    call_convert_api "${BASE_URL}/aview/files/${file}" "url" "pdf"
    call_convert_api "${BASE_URL}/aview/files/${file}" "url" "html"
done
print_section "4. Cache 효과 확인 테스트 (첫 번째 Office 파일 재실행)"
first_office_file="${office_files[0]}"
print_step "$first_office_file 재실행 (캐시 효과 확인)"

# 첫 번째 Office 파일만 다시 실행
call_convert_api "${first_office_file}" "path" "pdf"
call_convert_api "${first_office_file}" "path" "html"
call_convert_api "${BASE_URL}/aview/files/${first_office_file}" "url" "pdf"
call_convert_api "${BASE_URL}/aview/files/${first_office_file}" "url" "html"

echo "✅ Office 파일 재실행 완료 (캐시 효과 확인)"
print_step "Cache 상태 확인"
cache_stats
echo "✅ Cache 초기화 및 상태 확인 완료"


end_time=$(date +%s)
execution_time=$((end_time - start_time))

echo "/view 테스트"

print_section "5. View API 테스트"
print_step "모든 파일 타입 View 테스트"
for file in "${view_files[@]}"; do
    print_step "$file View 테스트 (path & url)"
    
    # Path parameter tests (output 파라미터 없음)
    call_view_api "${file}" "path"
    
    # URL parameter tests (output 파라미터 없음)  
    call_view_api "${file}" "url"
done

echo "✅ View API 테스트 완료"


print_section "테스트 완료"
echo "총 실행 시간: ${execution_time}초"
echo "========================================="