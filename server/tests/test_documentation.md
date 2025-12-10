# AI Server API 테스트 문서

## 개요

본 문서는 AI Server의 모든 API 엔드포인트에 대한 종합 테스트 문서입니다.

**테스트 범위:**
- Chat API (3개 시나리오)
- Recommendation API (1개 시나리오)
- Vectorization API (1개 시나리오)
- Admin API (6개 시나리오)

**총 11개 API 엔드포인트** 테스트

---

## 1. Chat API 테스트

### CHAT-01: 스트리밍 챗봇 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | CHAT-01 |
| **테스트 시나리오** | SSE 스트리밍 챗봇 응답 |
| **테스트 조건** | `POST /api/v1/chat/stream`<br/>- 유효한 요청 (user_id, session_id, message)<br/>- 선택적 keywords 파라미터<br/>- 스트리밍 응답 수신 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- SSE 스트리밍 응답<br/>- type: "token" - 토큰 단위 응답<br/>- type: "products" - 추천 상품 리스트<br/>- type: "keywords" - 관련 키워드<br/>- type: "done" - 완료 신호<br/><br/>**실패 케이스:**<br/>- type: "error" - 에러 메시지 |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | 스트리밍 중 에러 발생 시 "error" 이벤트 전송, 대화 히스토리 저장 실패 가능 |

**테스트 케이스:**
- ✅ `test_stream_chat_success` - 정상 스트리밍 응답
- ✅ `test_stream_chat_with_error` - 에러 처리
- ✅ `test_stream_chat_without_keywords` - keywords 없이 요청

---

### CHAT-02: 피드백 저장 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | CHAT-02 |
| **테스트 시나리오** | 사용자 피드백 저장 (좋아요/싫어요) |
| **테스트 조건** | `POST /api/v1/chat/feedback`<br/>- user_id, session_id, message_id, feedback 필수<br/>- product_id 선택적<br/>- feedback: "like" 또는 "dislike" |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- status: "success"<br/>- message: "피드백이 저장되었습니다."<br/><br/>**실패 케이스:**<br/>- 422 Validation Error (필수값 누락)<br/>- 500 Internal Server Error (DB 에러) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | 데이터베이스 연결 실패 시 피드백 저장 불가, 500 에러 반환 |

**테스트 케이스:**
- ✅ `test_save_feedback_like_with_product` - 상품 ID와 함께 좋아요
- ✅ `test_save_feedback_dislike_without_product` - 상품 ID 없이 싫어요
- ✅ `test_save_feedback_validation_error` - 필수값 누락
- ✅ `test_save_feedback_database_error` - DB 에러 처리

---

### CHAT-03: 대화 히스토리 조회 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | CHAT-03 |
| **테스트 시나리오** | 대화 히스토리 조회 (페이지네이션) |
| **테스트 조건** | `GET /api/v1/chat/history`<br/>- user_id, session_id 필수<br/>- limit (기본값: 5)<br/>- skip (기본값: 0) |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- history: 대화 내역 배열<br/>- 페이지네이션 적용<br/><br/>**실패 케이스:**<br/>- 500 Error (DB 에러) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB 연결 실패 시 500 에러, 히스토리 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_chat_history_success` - 정상 조회
- ✅ `test_get_chat_history_with_pagination` - 페이지네이션
- ✅ `test_get_chat_history_empty` - 빈 히스토리
- ✅ `test_get_chat_history_default_params` - 기본값 사용
- ✅ `test_get_chat_history_database_error` - DB 에러

---

## 2. Recommendation API 테스트

### REC-01: 맞춤형 금융상품 추천 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | REC-01 |
| **테스트 시나리오** | 사용자 ID 기반 맞춤형 금융상품 추천 |
| **테스트 조건** | `GET /api/v1/recommendations/{user_id}`<br/>- 사용자 임베딩 존재<br/>- Vector Search 실행<br/>- 예적금, 연금저축, 펀드 각 1개씩 추천 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- deposit_or_saving: 예금/적금 추천<br/>- annuity: 연금저축 추천<br/>- fund: 펀드 추천<br/>- 각 상품에 AI 생성 추천 이유 포함<br/><br/>**실패 케이스:**<br/>- 500 Error (임베딩 없음, DB 에러) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | 사용자 임베딩 미존재 시 추천 불가, MongoDB 연결 실패 시 500 에러 |

**테스트 케이스:**
- ✅ `test_get_recommendations_success` - 3개 상품 추천 성공
- ✅ `test_get_recommendations_with_ai_reasons` - AI 추천 이유 생성
- ✅ `test_get_recommendations_empty_results` - 매칭 상품 없음
- ✅ `test_get_recommendations_user_without_embedding` - 임베딩 없는 사용자
- ✅ `test_get_recommendations_mongodb_error` - MongoDB 에러
- ✅ `test_get_recommendations_vector_search_timeout` - Vector Search 타임아웃
- ✅ `test_get_recommendations_different_user_ids` - 다양한 user_id 테스트

---

## 3. Vectorization API 테스트

### VEC-01: 사용자 벡터화 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | VEC-01 |
| **테스트 시나리오** | 사용자 프로필 벡터화 및 임베딩 생성 |
| **테스트 조건** | `POST /api/v1/users/{user_id}/vectorize`<br/>- Spring Boot에서 사용자 정보 조회<br/>- 페르소나 텍스트 생성<br/>- Gemini 임베딩 생성<br/>- MongoDB에 저장 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- user_id: 사용자 ID<br/>- persona_text: 생성된 페르소나<br/>- status: "success"<br/><br/>**실패 케이스:**<br/>- 500 Error (사용자 없음, 임베딩 생성 실패, DB 에러) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | Spring Boot 연결 실패 시 사용자 정보 조회 불가, Gemini API 에러 시 임베딩 생성 실패, MongoDB 연결 실패 시 저장 불가 |

**테스트 케이스:**
- ✅ `test_vectorize_user_success` - 정상 벡터화
- ✅ `test_vectorize_user_persona_generation` - 페르소나 생성
- ✅ `test_vectorize_user_embedding_saved` - 임베딩 저장
- ✅ `test_vectorize_user_not_found` - 사용자 없음
- ✅ `test_vectorize_user_embedding_generation_failure` - 임베딩 생성 실패
- ✅ `test_vectorize_user_mongodb_connection_error` - MongoDB 에러
- ✅ `test_vectorize_user_spring_boot_connection_error` - Spring Boot 연결 에러
- ✅ `test_vectorize_multiple_users` - 다수 사용자 벡터화

---

## 4. Admin API 테스트

### ADMIN-01: 대시보드 전체 통계 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-01 |
| **테스트 시나리오** | 대시보드 전체 통계 조회 |
| **테스트 조건** | `GET /api/admin/stats/overview`<br/>- MongoDB Aggregation 실행<br/>- 총 대화, API 요청, 만족도, 활성 사용자 계산 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- total_chats: 총 대화 수<br/>- total_api_calls: 총 API 호출 수<br/>- satisfaction_rate: 만족도 (0-100)<br/>- active_users: 활성 사용자 수<br/><br/>**빈 DB:**<br/>- 200 OK (모든 값 0) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB 연결 실패 시 통계 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_dashboard_stats_success` - 정상 통계 조회
- ✅ `test_get_dashboard_stats_empty_database` - 빈 데이터베이스

---

### ADMIN-02: 대화 및 API 요청 추이 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-02 |
| **테스트 시나리오** | 월별 대화 및 API 요청 추이 조회 |
| **테스트 조건** | `GET /api/admin/stats/trends`<br/>- 월별 데이터 그룹핑<br/>- 최근 6개월 추이 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- trends: 월별 추이 배열<br/>  - date: "YYYY-MM"<br/>  - api_calls: API 호출 수<br/>  - user_chats: 사용자 대화 수<br/><br/>**빈 DB:**<br/>- 200 OK (빈 배열) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB Aggregation 실패 시 추이 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_dashboard_trends_success` - 정상 추이 조회
- ✅ `test_get_dashboard_trends_empty` - 빈 데이터

---

### ADMIN-03: 피드백 분포 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-03 |
| **테스트 시나리오** | 좋아요/싫어요 피드백 분포 조회 |
| **테스트 조건** | `GET /api/admin/stats/feedback`<br/>- 피드백 타입별 집계 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- like: 좋아요 수<br/>- dislike: 싫어요 수<br/><br/>**빈 데이터:**<br/>- 200 OK (모든 값 0) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB Aggregation 실패 시 분포 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_feedback_stats_success` - 정상 분포 조회
- ✅ `test_get_feedback_stats_no_data` - 피드백 없음

---

### ADMIN-04: 사용자별 AI 사용 통계 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-04 |
| **테스트 시나리오** | 사용자별 AI 사용 통계 조회 (페이지네이션, 검색) |
| **테스트 조건** | `GET /api/admin/users`<br/>- page (기본값: 1)<br/>- limit (기본값: 10)<br/>- search (이름 또는 ID 검색)<br/>- N+1 쿼리 방지 (단일 Aggregation) |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- users: 사용자 통계 배열<br/>  - user_id, name, login_id<br/>  - chat_count, api_count<br/>  - likes, dislikes, satisfaction<br/>- total: 전체 사용자 수<br/>- page, limit<br/><br/>**검색:**<br/>- 이름/ID로 필터링된 결과 |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MySQL 연결 실패 시 사용자 목록 조회 불가, MongoDB 연결 실패 시 통계 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_user_stats_success` - 정상 통계 조회
- ✅ `test_get_user_stats_with_search` - 검색 기능
- ✅ `test_get_user_stats_pagination` - 페이지네이션

---

### ADMIN-05: 챗봇 대화 로그 목록 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-05 |
| **테스트 시나리오** | 챗봇 대화 로그 목록 조회 (페이지네이션, 검색) |
| **테스트 조건** | `GET /api/admin/logs`<br/>- page (기본값: 1)<br/>- limit (기본값: 10)<br/>- search (사용자 ID 검색)<br/>- 최근 대화순 정렬<br/>- 마지막 메시지 50자 제한 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- logs: 로그 배열<br/>  - user_id, name<br/>  - last_message (최대 50자)<br/>  - last_active<br/>  - total_messages<br/>- page, limit<br/><br/>**검색:**<br/>- user_id로 필터링 |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB 연결 실패 시 로그 조회 불가, MySQL 연결 실패 시 사용자 이름 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_chat_logs_success` - 정상 로그 조회
- ✅ `test_get_chat_logs_with_search` - user_id 검색
- ✅ `test_get_chat_logs_message_truncation` - 메시지 50자 제한

---

### ADMIN-06: 특정 사용자 대화 상세 내역 API

| 항목 | 내용 |
|------|------|
| **기능 ID** | ADMIN-06 |
| **테스트 시나리오** | 특정 사용자의 전체 대화 상세 내역 조회 |
| **테스트 조건** | `GET /api/admin/logs/{user_id}`<br/>- page (기본값: 1)<br/>- limit (기본값: 20)<br/>- 최신순 정렬 |
| **예상 결과** | **성공 케이스:**<br/>- 200 OK<br/>- history: 대화 내역 배열<br/>  - role: "user" 또는 "assistant"<br/>  - content: 메시지 내용<br/>  - timestamp: 시간<br/>- total: 전체 메시지 수<br/>- page, limit<br/><br/>**빈 히스토리:**<br/>- 200 OK (빈 배열) |
| **단위 테스트 결과** | 통과 |
| **Fail 동작** | MongoDB 연결 실패 시 대화 내역 조회 불가 |

**테스트 케이스:**
- ✅ `test_get_user_chat_history_success` - 정상 내역 조회
- ✅ `test_get_user_chat_history_pagination` - 페이지네이션
- ✅ `test_get_user_chat_history_empty` - 빈 히스토리

---

## 테스트 실행 방법

### 전체 테스트 실행

```bash
# server/ 디렉토리에서 실행
pytest tests/ -v
```

### 모듈별 테스트 실행

```bash
# Chat API 테스트
pytest tests/test_chat_api.py -v

# Recommendation API 테스트
pytest tests/test_recommendation_api.py -v

# Vectorization API 테스트
pytest tests/test_vectorization_api.py -v

# Admin API 테스트
pytest tests/test_admin_api.py -v
```

### 커버리지 리포트 생성

```bash
pytest tests/ --cov=app --cov-report=html
```

---

## 테스트 통계

| 모듈 | 테스트 시나리오 수 | 테스트 케이스 수 | 상태 |
|------|-------------------|-----------------|------|
| Chat API | 3 | 12 | ✅ 통과 |
| Recommendation API | 1 | 7 | ✅ 통과 |
| Vectorization API | 1 | 8 | ✅ 통과 |
| Admin API | 6 | 11 | ✅ 통과 |
| **합계** | **11** | **38** | **✅ 통과** |

---

## 주요 테스트 포인트

### 1. SSE 스트리밍 테스트
- 비동기 스트리밍 응답 처리
- 다양한 이벤트 타입 검증 (token, products, keywords, done, error)
- 에러 발생 시 graceful degradation

### 2. 페이지네이션 테스트
- limit, skip/page 파라미터 검증
- 기본값 동작 확인
- 빈 결과 처리

### 3. 검색 기능 테스트
- 이름, ID 검색 필터링
- 부분 일치 검색
- 빈 검색어 처리

### 4. 에러 처리 테스트
- 데이터베이스 연결 실패
- 외부 API 연결 실패 (Spring Boot, Gemini)
- 유효성 검증 실패
- 타임아웃 처리

### 5. N+1 쿼리 방지
- MongoDB Aggregation 사용
- 단일 쿼리로 관련 데이터 조회
- 성능 최적화 검증

---

## 의존성

테스트 실행을 위해 다음 패키지가 필요합니다:

```txt
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-mock>=3.10.0
httpx>=0.27.0  # FastAPI TestClient 의존성
```

설치:
```bash
pip install pytest pytest-asyncio pytest-mock
```

---

## 참고사항

1. **Mock 사용**: 모든 테스트는 외부 의존성(MongoDB, MySQL, Spring Boot, Gemini API)을 Mock으로 처리하여 독립적으로 실행됩니다.

2. **비동기 테스트**: Chat API의 SSE 스트리밍은 `pytest-asyncio`를 사용하여 비동기 테스트를 수행합니다.

3. **테스트 격리**: 각 테스트는 독립적으로 실행되며 서로 영향을 주지 않습니다.

4. **데이터 픽스처**: `conftest.py`에 정의된 공통 픽스처를 사용하여 테스트 데이터를 관리합니다.
