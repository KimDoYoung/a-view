# a-view

## 개요

- [AssetERP](http://www.k-fs.co.kr/product2.do)에서는 구글의 gview를 이용해서 excel, word, powerpoint 파일을 보여주었는데, 구글이 더 이상 gview서비스를 원활히 지원하지 않아서 
자체적으로 개발하기로 하였습니다.
- 2가지 방식을 고려했는데, excel, word, powerpoint를 해석하는 1)**개별 파이썬 라이브러리를 사용하여 변환하는 방식**과 2)**libreoffice 라이브러리를 사용하는 방식**임
- 본 프로젝트는 libreoffice 라이브러리를 사용하여 개발하기로 하였습니다.

## 설계

### dashboard제공
- index.html에 dashboard 기능제공
- 시스템상태 확인
- 통계 확인
- 캐쉬 상태 및 관리 기능 제공

### 자체적인 테스트 기능
- 타 시스템과연계되지 않고 자체적으로 파일을 업로드한 후에 테스트 가능하도록 기능 및 UI제공
- 타 시스템이 URL을 입력하여 테스트할 수 있도록 함

### 캐쉬 사용

- redis를 사용하여 캐싱
- 원본파일과 변환된 파일을 파일시스템에서 보관
- 파일명은 hash함수를 사용해서 작성
- 주어진 시간(24시간)만 보관

### 통계 및 스케줄링

- sqlite db를 사용하여 일자별, 파일종류별 통계
- 자체적인 스케줄러를 갖음
- 매일 새벽에 전날 통계 작성
- 매주 일요일에 1주일 통계 작성

### API 설계 개요

1. convert와 view 2개의 주요 api를 제공한다.
2. convert는 오피스 파일들(excel, words, powerpoint)를 대상으로 pdf또는 html로 변환한 후 변환된 url을 제공한다.
3. view는 오피스 파일들을 포함한 다양한 파일 포맷을 대상으로 pdf또는 html등으로 변환한 후 보기기능을 지원하는 웹페이지를 제공한다.

| API     | 대상                                | 변환방식   | 제공방식  |
|---------|-------------------------------------|------------|-----------|
| convert | 오피스파일                          | 사용자지정 | JSON      |
| view    | 오피스파일 외 이미지, Markdown, CSV, Text 등 | 대상에 따라 자동 | Web Page |

### API convert

1. get, post 지원
2. param
   1. url or path  : url로 파일을 지정, path는 동일 서버에 사용자 웹서비스와 a-view서비스가 존재하고 물리적 disk를 공유시 사용가능
   2. output : pdf또는 html을 지정할 수 있음.
3. response
    1. json 형태로 제공됨
    2. success, url, message가 제공됨
4. example
   ```bash
    # 성공시
    curl "http://a-view-host:8003/convert?path=c:\\tmp\\sample\\11.docx&output=pdf"
    {"success":true,"url":"http://a-view-host:8003/aview/pdf/5165f18545b0e73fd8b3e3bb69a236d8.pdf","message":"로칼 파일이 OutputFormat.PDF 형식으로 변환되었습니다"}
    curl "http://a-view-host:8003/convert?url=http://user-host:8003/static/files/AssetERP/1.docx&output=pdf"
    {"success":true,"url":"http://a-view-host:8003/aview/pdf/25115ce96ff4f71d9d8c66bf7d0d74da.pdf","message":"URL 문서가 OutputFormat.PDF 형식으로 변환 되었습니다"}    
    #  에러시
    curl "http://a-view-host:8003/convert?path=c:\\tmp\\sample\\aa.docx&output=pdf"
    {"success":false,"url":"","message":"입력 오류: 1 validation error for ConvertParams\npath\n  Value error, 파일이 존재하지 않습니다: c:\\tmp\\sample\\aa.docx [type=value_error, input_value='c:\\\\tmp\\\\sample\\\\aa.docx', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/value_error"}    
   ```

### API view

1. get방식만 제공
2. param : url or path  : url로 파일을 지정, path는 동일 서버에 사용자 웹서비스와 a-view서비스가 존재하고 물리적 disk를 공유시 사용가능
3. response : 웹페이지
4. param에 따라서 자동으로 output을 제공

| 대상                         | Output 포맷 |
|------------------------------|-------------|
| 오피스 파일들 (Excel, Word, PPT) | PDF         |
| TXT(.txt)                          | HTML        |
| CSV(.csv)                          | HTML        |
| 이미지파일들(.jpg, .png)             | HTML        |
| Markdown(.md)                     | HTML        |


## 배포

- docker를 사용하여 배포
- 3개 환경이 이 존재함. 윈도우에서 개발(.env.local), 리눅스 테스트서버(.env.test), 리눅스 운영서버(.env.real)
- 개발(윈도우)에도 docker가 설치되어 있음.
- 리눅스 테스트 서버에 사용자 aview를 생성, 홈 디렉토리는 /data1/aview 임
- 운영 리눅스에는 SSL파일을 .env.real에 기술하여야함.
- 기본명령어들
```bash
docker compose -f docker-compose.local.yml build
# 기동
docker compose -f docker-compose.local.yml up -d
# 로그
docker compose -f docker-compose.local.yml logs -f aview
```

### deploy.sh을 통한 docker 배포

- docker명령어를 모아서 deploy.sh을 작성함.
- 사용법
```bash
# 기본 사용
./deploy.sh # 도움말을 볼 수 있음
./deploy.sh up local                    # 일반 시작
./deploy.sh build test --no-cache       # 캐시 없이 빌드
./deploy.sh up local --force-recreate   # 강제 재생성

# 완전 삭제
./deploy.sh clean-all local             # 모든 aview 리소스 삭제

# 명령어 확인만
./deploy.sh build local --dry-run       # 실행할 명령어만 출력
./deploy.sh clean-all local --dry-run   # 삭제할 명령어들 출력
```


## 설정

- 환경설정 `A_VIEW_MODE` 의 값이 development | production 인지에 따라서.
- .env .env.production 을 반영하여 settings가 설정됨

## 방식

- AssetERP에서 ifram 으로 **http://g-view-host:8003/view?url=https://.../abc.xlsx** 호출
- 사용방법
```text
a-view는 assertERP 시스템에서 호출한다. 즉 AssetERP에서   localhost:8003/aview?url=https://asserterp-host/files/a.xlsx와 같이 호출한다. 그러면 localhost:8003(a-view)에서 그 파일을 다운로드해서 libre를 이용하여 변환한 후에 보여줘야한다. 이것을 테스트하기 위해서 나는 AssetERP(자바베이스의 web application)을 대신하는 web-application을 만들 필요가 있는가? 아니면 그냥 a-view로 그것을 갈음하여 테스트 가능한가?
```

```text
http://a-view-host:8003/aview?url=http://asset-erp-user-host:8003/static/files/AssetERP/1.xlsx
```

## 설치

1. [radis](https://redis.io/)를 cache 용으로 사용함.
2. [libreoffice](https://www.libreoffice.org/) 를 다운해서 설치 

## redis

- docker에서 실행
  ```bash
  docker ps
  docker stop redis-aview
  docker run -d --name redis-aview -p 6379:6379 redis:latest
  docekr rm redis-aview
  docker run -d --name redis-aview -p 6379:6379 redis:latest
  ```

