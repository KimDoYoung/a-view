#!/bin/bash


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
# Cache 상태 확인 함수
cache_stats() {
    cache_stats_response=$(curl -s -w "\n%{http_code}\n%{time_total}" "${BASE_URL}/cache/stats")
    cache_stats_http_code=$(echo "$cache_stats_response" | tail -n 2 | head -n 1)
    cache_stats_time=$(echo "$cache_stats_response" | tail -n 1)
    cache_stats_body=$(echo "$cache_stats_response" | head -n -2)

    echo "HTTP Code: $cache_stats_http_code"
    echo "Response Time: ${cache_stats_time}s"
    echo "Response: $cache_stats_body"
    echo "------------------------------------------"
}
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
cache_stats
echo "✅ Cache 초기화 완료"

#  convert를 호출할 수 없는 파일들을 호출했었을 때 success:fasle
for file in "${required_files[@]}"; do
    echo "------------------------------------------"
    echo "convert ERROR API 호출 - ${file}"
    url="${BASE_URL}/convert?path=${SAMPLE_PATH}/${file}&output=pdf"
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | head -n -2)

    echo "HTTP Code: $http_code"
    echo "Response Time: ${time_total}s"
    echo "Response: $body"
    echo "------------------------------------------"

    if [[ "$http_code" != "200" ]]; then
        echo "❌ View API 호출 실패 (HTTP $http_code)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        exit 1
    fi
    # $body에 "success":false가 포함되어 있어야함 없으면 데러표시 종료
    if [[ "$body" != *'"success":false'* ]]; then
        echo "❌ View API 호출 실패 (응답에 success:false 없음)"
        echo "요청 URL: $url"
        echo "응답 내용: $body"
        exit 1
    fi
    echo "✅ convert 잘못된 파일 호출 OK : $file"
    echo "------------------------------------------"
done


# for file in "${view_files[@]}"; do
#     print_section "3. View API 호출 - $file"
#     url="${BASE_URL}/convert?path=${SAMPLE_PATH}/${file}&output=pdf"
#     response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$url")
#     http_code=$(echo "$response" | tail -n 2 | head -n 1)
#     time_total=$(echo "$response" | tail -n 1)
#     body=$(echo "$response" | head -n -2)

#     echo "HTTP Code: $http_code"
#     echo "Response Time: ${time_total}s"
#     echo "Response: $body"
#     echo "------------------------------------------"

#     if [[ "$http_code" != "200" ]]; then
#         echo "❌ View API 호출 실패 (HTTP $http_code)"
#         echo "요청 URL: $url"
#         echo "응답 내용: $body"
#         exit 1
#     fi
# done