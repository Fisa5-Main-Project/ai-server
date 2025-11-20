# KnowHow RAG(검색 증강 생성) AI 서버입니다.

## airflow/

본 파이프라인의 핵심 목적은 **AI 기반 추천 시스템(RAG)**에 필요한 최신 데이터를 완전 자동화된 방식으로 공급하는 것입니다.

수집된 데이터는 AI 모델이 사용자의 상황과 키워드(예: "여행", "연금")에 맞는 최적의 상품을 실시간으로 검색하고 추천하는 데 사용됩니다.

🗂️ 데이터 소스
본 파이프라인은 2개의 주요 기관으로부터 총 4종의 금융 데이터를 수집합니다.

금융감독원 (FSS) Open API

정기예금: 금리, 우대조건, 가입 대상 등

적금: 금리, 납입 방식, 우대조건 등

연금저축: 상품 유형, 공시 이율, 운용사 등

한국벤처투자 (KVIC) 펀드 현황

펀드 정보: (향후 추가 예정) 벤처투자 펀드의 현황 및 정보를 크롤링 또는 API를 통해 수집합니다.

⚙️ 기술 스택 및 실행
워크플로우: Apache Airflow (Docker Compose 기반)

데이터베이스: MongoDB (RAG VectorDB로 활용)

핵심 라이브러리: Python, Requests, Pymongo

실행 방법
Airflow 실행:

Bash

docker-compose up -d --build

## server/

이 서버는 Spring Boot 백엔드 서버의 요청을 받아, MongoDB (VectorDB)에 저장된 금융 상품 데이터를 기반으로 Gemini LLM을 통해 사용자 맞춤형 상품을 추천하는 API를 제공합니다.

🚀 주요 기능
실시간 금융 상품 추천: LangChain과 Gemini API를 사용한 RAG 파이프라인을 통해 상품 추천

VectorDB 연동: MongoDB Atlas Vector Search를 활용하여 사용자의 자연어 쿼리(키워드)와 가장 유사한 상품 검색

비동기 API: FastAPI를 기반으로 비동기(Async) 처리를 지원하여 빠른 응답 속도 보장

💻 기술 스택
Server: FastAPI, Uvicorn

LLM (RAG): LangChain, Google Gemini

Embedding: Sentence-Transformers (HuggingFace)

VectorDB: MongoDB (with langchain-mongodb)

Configuration: Pydantic-settings

Infra: Docker

🏃 실행 방법 (온프레미스 서버 기준)

1. 프로젝트 복제 및 이동
2. 민감 정보 설정
   API 키와 DB 접속 정보는 .env 파일로 관리합니다.

먼저 .env.example 파일을 복사하여 .env 파일을 생성합니다.

### .env.example 파일을 .env 파일로 복사

cp .env.example .env

### nano 편집기로 .env 파일 열기

nano .env
.env 파일에 실제 키와 주소를 입력합니다.

### 3. 의존성 설치

pip install -r requirements.txt 4. AI 서버 실행 (팀 포트: 8304)

### --port 8304 : 4팀 AI 서버 포트

uvicorn app.main:app --host 0.0.0.0 --port 8304 --reload
