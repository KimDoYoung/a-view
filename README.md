# a-view

## 개요

- AssetERP에서는 구글의 gview를 이용해서 excel, word, powerpoint 파일을 보여주었는데, 구글이 더 이상 gview서비스를 원활히 지원하지 않아서 
자체적으로 개발하기로 함.
- 2가지 방식이 있는데, excel, word, powerpoint를 해석하는 개별 파이썬 라이브러리를 사용하여 변환하는 방식과 libreoffice 라이브러리를 사용하는 방식임
- 본 프로젝트는 libreoffice 라이브러리를 사용하여 개발함.

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