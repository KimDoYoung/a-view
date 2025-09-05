# a-view

## 개요

- AssetERP에서는 구글의 gview를 이용해서 excel, word, powerpoint 파일을 보여주었는데, 구글이 더 이상 gview서비스를 원활히 지원하지 않아서 
자체적으로 개발하기로 함.
- 2가지 방식이 있는데, excel, word, powerpoint를 해석하는 개별 파이썬 라이브러리를 사용하여 변환하는 방식과 libreoffice 라이브러리를 사용하는 방식임
- 본 프로젝트는 libreoffice 라이브러리를 사용하여 개발함.

## 설계

### 설계 개요

1. convert와 view 2개의 주요 api를 제공한다.
2. convert는 오피스 파일들(excel, words, powerpoint)를 대상으로 pdf또는 html로 변환한 후 변환된 url을 제공한다.
3. view는 오피스 파일들을 포함한 다양한 파일 포맷을 대상으로 pdf또는 html등으로 변환한 후 보기기능을 지원하는 웹페이지를 제공한다.

| API     | 대상                                | 변환방식   | 제공방식  |
|---------|-------------------------------------|------------|-----------|
| convert | 오피스파일                          | 사용자지정 | JSON      |
| view    | 오피스파일 외 이미지, Markdown, CSV, Text 등 | 대상에 따라 자동 | Web Page |

### convert

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
    curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\11.docx&output=pdf"
    {"success":true,"url":"http://127.0.0.1:8003/aview/pdf/5165f18545b0e73fd8b3e3bb69a236d8.pdf","message":"로칼 파일이 OutputFormat.PDF 형식으로 변환되었습니다"}
    curl "http://localhost:8003/convert?url=http://localhost:8003/static/files/AssetERP/1.docx&output=pdf"
    {"success":true,"url":"http://127.0.0.1:8003/aview/pdf/25115ce96ff4f71d9d8c66bf7d0d74da.pdf","message":"URL 문서가 OutputFormat.PDF 형식으로 변환 되었습니다"}    
    #  에러시
    curl "http://localhost:8003/convert?path=c:\\tmp\\sample\\aa.docx&output=pdf"
    {"success":false,"url":"","message":"입력 오류: 1 validation error for ConvertParams\npath\n  Value error, 파일이 존재하지 않습니다: c:\\tmp\\sample\\aa.docx [type=value_error, input_value='c:\\\\tmp\\\\sample\\\\aa.docx', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/value_error"}    
   ```

### view

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

### view 테스트

```bash
http://localhost:8003/view?path=c:\\tmp\\sample\\11.docx
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
- static/files/AssetERP에 파일 1.xlsx를 올려놓고 
```text
http://localhost:8003/aview?url=http://localhost:8003/static/files/AssetERP/1.xlsx
```


## redis

- docker에서 실행
  ```bash
  docker ps
  docker stop redis-aview
  docker run =d --name redis-aview -p 6379:6379 redis:latest
  docekr rm redis-aview
  docker run -d --name redis-aview -p 6379:6379 redis:latest
  ```