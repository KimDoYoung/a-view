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
