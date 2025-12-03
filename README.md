# 노후하우 AI 서버 (KnowWhoHow AI Server)

## 1. 프로젝트 개요

본 프로젝트는 크게 **데이터 파이프라인(Airflow)** 과 **API 서버(FastAPI)** 로 구성되어 있습니다.

AI 서버는 사용자의 마이데이터와 금융 성향을 전처리 및 벡터화하여, **RAG(Retrieval-Augmented Generation)**를 활용하여 개인 맞춤형 금융 상품(예금, 적금, 펀드, 연금)을 추천하고 상담해주는 서버입니다.

특히 **Airflow**를 활용하여 금융위원회, 금융감독원 등 **다양한 공공 데이터 OpenAPI**로부터 최신 금융 상품 정보를 주기적으로 수집하고 전처리하여 데이터의 **신선도(Freshness)**를 유지합니다. 수집된 데이터와 벡터 임베딩은 Cloud NoSQL DB인 **MongoDB Atlas**에 적재되어, 고성능의 하이브리드 검색(Hybrid Search)을 지원합니다.

## 2. 주요 기능
- **개인 맞춤형 상품 추천**: 사용자의 자산 현황, 투자 성향, 연령대 등을 분석하여 최적의 금융 상품 추천.
- **지능형 챗봇 상담**: 금융 상품에 대한 질의응답을 실시간 스트리밍으로 제공.
- **데이터 최신화 (ETL)**: 금융위원회 및 각 금융사 데이터를 주기적으로 수집, 전처리, 임베딩하여 벡터 DB에 적재.
- **유저 페르소나 벡터화**: 사용자 데이터를 텍스트화 및 벡터화하여 유사도 검색에 활용.

## 3. 기술 스택 (Tech Stack)

### 3.1. Server (EC2 / Local)
- **Framework**: FastAPI
- **Language**: Python 3.10+
- **AI & LLM**:
    - LangChain (Core, Community, Google GenAI)
    - Google Gemini Pro (Generative AI)
    - LangGraph (Agent Workflow)
- **Database**:
    - MongoDB Atlas (Vector Store & Data Lake)
    - MySQL (User Data - Read Only)
- **Deployment**: Docker, Uvicorn

### 3.2. Airflow (On-Premise)
- **Orchestrator**: Apache Airflow 3.1.1
- **Executor**: Celery Executor
- **Message Broker**: Redis
- **Metadata DB**: PostgreSQL
- **Key Libraries**:
    - `pandas`, `requests` (Data Processing)
    - `pymongo` (DB Interaction)
    - `langchain-google-genai` (Embedding Generation)

## 4. 디렉토리 구조
```bash
main-project-ai/
├── airflow/                  # Airflow 관련 설정 및 DAG
│   ├── dags/                 # 데이터 파이프라인 (ETL) 정의
│   ├── config/               # Airflow 설정 파일
│   ├── Dockerfile            # Airflow 커스텀 이미지 빌드 설정
│   └── requirements.txt      # Airflow 의존성 패키지
├── server/                   # AI API 서버
│   ├── app/                  # FastAPI 애플리케이션 코드
│   │   ├── api/              # API 라우터 (v1)
│   │   ├── core/             # 설정(Config) 및 공통 모듈
│   │   ├── services/         # 비즈니스 로직 (RAG, Chatbot 등)
│   │   └── main.py           # 앱 진입점
│   ├── Dockerfile            # Server 이미지 빌드 설정
│   └── requirements.txt      # Server 의존성 패키지
├── docker-compose.local.yml  # 로컬 개발 환경 실행 설정 (Airflow + Server + Mongo)
└── scripts/                  # 유틸리티 스크립트
```

## 5. APIs
주요 API 엔드포인트는 다음과 같습니다. 상세 명세는 서버 실행 후 `/docs`에서 확인할 수 있습니다.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | 서버 상태 및 버전 정보 확인 |
| `GET` | `/api/v1/recommendations/{user_id}` | 특정 유저를 위한 맞춤형 금융 상품 추천 |
| `POST` | `/api/v1/chat/stream` | 챗봇과의 대화 (스트리밍 응답) |
| `POST` | `/api/v1/chat/feedback` | 추천/상담 결과에 대한 피드백 저장 |
| `POST` | `/api/v1/users/{user_id}/vectorize` | 유저 데이터 벡터화 및 갱신 (트리거) |

### 5.1. Admin APIs
관리자 페이지를 위한 통계 및 로그 조회 API입니다.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/admin/stats/overview` | 대시보드 전체 통계 조회 |
| `GET` | `/api/v1/admin/stats/trends` | 대화 및 API 요청 추이 조회 |
| `GET` | `/api/v1/admin/stats/feedback` | 피드백 분포 조회 |
| `GET` | `/api/v1/admin/users` | 사용자별 AI 사용 통계 조회 |
| `GET` | `/api/v1/admin/logs` | 챗봇 대화 로그 목록 조회 |
| `GET` | `/api/v1/admin/logs/{user_id}` | 특정 사용자의 대화 상세 내역 조회 |

## 6. 배포 정보
- **Production URL**: [https://knowwhohow.cloud](https://knowwhohow.cloud)
- **Dev/Client URL**: [https://knowwhohow.site](https://knowwhohow.site)

## 7. 실행 가이드 (로컬 환경)

### 사전 요구사항
- Docker 및 Docker Compose 설치
- `.env` 파일 설정 (각 디렉토리의 `.env.example` 참고)

### Airflow 실행
```bash
# airflow 루트에서 실행
docker-compose up -d --build
```

### 개별 실행 (Server Only)
```bash
cd server
pip install -r requirements.txt

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 8. 결과
- **API Server**: [http://localhost:8000](http://localhost:8000) 접속 시 서버 상태 확인 가능.
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs) 에서 Swagger UI 확인.
- **Airflow Webserver**: [http://localhost:8080](http://localhost:8080) 접속 (ID/PW: `airflow`/`airflow` 설정 시).
