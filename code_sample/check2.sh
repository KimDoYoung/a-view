#!/bin/bash

###########################################
# 함수 정의
###########################################

# 일시정지 함수
pause() {
    echo ""
    echo "잠시 멈춤.... 계속 ENTER or Ctrl+C 종료"
    read -n 1 -s
    echo ""
}
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
    if curl -s -f --connect-timeout 5 --max-time 10 "$base_url" > /dev/null 2>&1; then
        echo "OK: 서버가 정상적으로 응답합니다."
        return 0
    else
        echo "ERROR: 서버에 연결할 수 없습니다."
        echo "다음을 확인해주세요:"
        echo "  1. 서버 실행 여부"
        echo "  2. 포트 8003 개방 여부"
        echo "  3. 방화벽 설정"
        echo "  4. URL 확인: $base_url"
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

# Python 없는 경우 fallback URL 인코딩
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

# 안전한 URL 인코딩 (Python 우선, 없으면 fallback)
safe_url_encode() {
    local string="$1"
    if command -v python3 &> /dev/null; then
        python3 -c "import urllib.parse; print(urllib.parse.quote('$string'))" 2>/dev/null && return
    fi
    if command -v python &> /dev/null; then
        python -c "import urllib; print urllib.quote('$string')" 2>/dev/null && return
    fi
    url_encode_fallback "$string"
}

# Convert API 호출 함수
call_convert_api() {
    local arg1="$1"
    local arg2="$2"
    local arg3="$3"
    local url=""
    local description=""

    if [[ "$arg1" == http* ]]; then
        local base_url="$arg1"
        local param_type="$arg2"
        local output_format="$arg3"
        if [[ "$param_type" == "url" ]]; then
            url="${BASE_URL}/convert?url=$(safe_url_encode "$base_url")&output=$output_format"
            description="Convert via URL to $output_format"
        elif [[ "$param_type" == "path" ]]; then
            url="${BASE_URL}/convert?path=$(safe_url_encode "$base_url")&output=$output_format"
            description="Convert via PATH to $output_format"
        else
            url="$arg1"
            description="${arg2:-API 호출}"
        fi
    else
        local filename="$arg1"
        local param_type="$arg2"
        local output_format="$arg3"
        if [[ "$param_type" == "path" ]]; then
            local full_path="${SAMPLE_PATH}/${filename}"
            url="${BASE_URL}/convert?path=$(safe_url_encode "$full_path")&output=$output_format"
            description="$filename → $output_format (path)"
        elif [[ "$param_type" == "url" ]]; then
            local file_url="${BASE_URL}/aview/files/${filename}"
            url="${BASE_URL}/convert?url=$(safe_url_encode "$file_url")&output=$output_format"
            description="$filename → $output_format (url)"
        else
            url="$arg1"
            description="${arg2:-API 호출}"
        fi
    fi

    echo "[$description]"
    echo "Request URL: $url"

    local response
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
    local http_code time_total body
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -2)

    echo "HTTP Code: $http_code"
    echo "Response Time: ${time_total}s"
    if [[ "$body" == *"<html"* ]] || [[ "$body" == *"<!DOCTYPE"* ]]; then
        echo "Response: [HTML Content - ${#body} bytes]"
        echo "Preview: ${body:0:100}..."
    else
        echo "Response: $body"
    fi
    # Response body를 temp 파일로 저장
    if [[ "$param_type" == "path" ]] || [[ "$param_type" == "url" ]]; then
        local safe_filename=$(echo "$filename" | sed 's/[^a-zA-Z0-9._-]/_/g')
        local temp_file="${TENP_DIR}/${safe_filename}_${param_type}_${output_format}.json"
        echo "$body" > "$temp_file"
        echo "Response saved to: $temp_file"
    fi
    if [[ "$http_code" != "200" ]]; then
        echo "❌ API 호출 실패 (HTTP $http_code)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        exit 1
    fi
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
}

# View API 호출 함수
call_view_api() {
    local filename="$1"
    local param_type="$2"
    local url=""
    local description=""

    if [[ "$param_type" == "path" ]]; then
        local full_path="${SAMPLE_PATH}/${filename}"
        url="${BASE_URL}/view?path=$(safe_url_encode "$full_path")"
        description="$filename → View (path)"
    elif [[ "$param_type" == "url" ]]; then
        local file_url="${BASE_URL}/aview/files/${filename}"
        url="${BASE_URL}/view?url=$(safe_url_encode "$file_url")"
        description="$filename → View (url)"
    fi

    echo "[$description]"
    echo "Request URL: $url"

    local response
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
    local http_code time_total body
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -2)

    echo "HTTP Code: $http_code"
    echo "Response Time: ${time_total}s"
    if [[ "$body" == *"<html"* ]] || [[ "$body" == *"<!DOCTYPE"* ]]; then
        echo "Response: [HTML Content - ${#body} bytes]"
        echo "Preview: ${body:0:100}..."
    else
        echo "Response: $body"
    fi

    if [[ "$http_code" != "200" ]]; then
        echo "❌ View API 호출 실패 (HTTP $http_code)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        exit 1
    fi
}

###########################################
# 실행 로직 (main)
###########################################

echo "========================================="
echo "A-View API Test Script"
echo "========================================="
start_time=$(date +%s)

BASE_URL="http://localhost:8003"
SAMPLE_PATH="c:/tmp/aview/files"
TENP_DIR="c:/tmp/aview/temp"

# 임시 디렉토리 준비
[ ! -d "$TENP_DIR" ] && mkdir -p "$TENP_DIR"
rm -f "$TENP_DIR"/*

# 서버 연결 상태 확인
print_section "0. 서버 연결 상태 확인"
if ! check_server_connection "$BASE_URL"; then
    exit 1
fi
echo "✅ 서버연결 확인"

# 필수 파일 확인
print_section "1. 필수 파일 존재 여부 확인"
required_files=("1.jpg" "1.csv" "1.txt" "1.md" "1.png" "1.pdf")
office_files=("1.docx" "2.pptx" "3.xlsx")
view_files=("${required_files[@]}" "${office_files[@]}")
missing_files=()

for file in "${view_files[@]}"; do
    file_path="${SAMPLE_PATH}/${file}"
    if ! check_file_exists "$file_path" "$file"; then
        missing_files+=("$file")
    else
        echo "OK: $file"
    fi
done
if [ ${#missing_files[@]} -gt 0 ]; then
    echo "필수 파일 누락: ${missing_files[*]}"
    exit 1
fi
echo "✅ 모든 필수 파일 확인 완료"
# Cache 초기화
print_section "2. Cache 초기화"
cache_response=$(curl -X POST -s -w "\n%{http_code}\n%{time_total}" "${BASE_URL}/cache/clear-all?confirm=true")
echo "$cache_response"
print_step "Cache 상태 확인"
cache_stats
echo "✅ Cache 초기화 완료"

# Office Convert 테스트
print_section "3. Office 문서 Convert 테스트"
for file in "${office_files[@]}"; do
    print_step "$file to PDF/HTML"
    call_convert_api "$file" "path" "pdf"
    call_convert_api "$file" "path" "html"
    call_convert_api "${BASE_URL}/aview/files/${file}" "url" "pdf"
    call_convert_api "${BASE_URL}/aview/files/${file}" "url" "html"
done
pause
# Cache 효과 확인
print_section "4. Cache 효과 확인"
first_office_file="${office_files[0]}"
call_convert_api "$first_office_file" "path" "pdf"
call_convert_api "$first_office_file" "path" "html"
call_convert_api "${BASE_URL}/aview/files/${first_office_file}" "url" "pdf"
call_convert_api "${BASE_URL}/aview/files/${first_office_file}" "url" "html"
cache_stats

# View API 테스트
print_section "5. View API 테스트"
for file in "${view_files[@]}"; do
    call_view_api "$file" "path"
    call_view_api "$file" "url"
done

# 총 실행시간 출력
end_time=$(date +%s)
execution_time=$((end_time - start_time))
print_section "테스트 완료"
echo "총 실행 시간: ${execution_time}초"
