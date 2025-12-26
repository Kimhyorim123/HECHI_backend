# BookStopper API Contract (v1)

## 버전 정책
- 파일: `openapi-v1.json`
- 규칙: 하위 호환 깨질 때 `v2`, 단순 필드 추가는 `v1.1`, `v1.2` 식 패치 버전으로.
- 변경 로그는 아래 `Changelog` 섹션에 Append.

## 전달 방식
프론트는 정적 파일을 받아 다음 중 하나로 사용:
1. 로컬 import 후 Swagger / Redoc 뷰어에 로드
2. CI 파이프라인에서 lint (e.g. `speccy`, `openapi-cli`) 실행

## 인증
- 모든 보호된 엔드포인트: `Authorization: Bearer <access_token>` 헤더 필요
- 토큰 발급: `/auth/login`
- 갱신: `/auth/refresh`

### 자동로그인(쿠키 기반)
- 로그인 시 `remember_me: true`를 보내면 서버가 `refresh_token`을 HttpOnly 쿠키로 설정합니다.
- 액세스 토큰 만료 시, 본문 없이 `/auth/refresh`를 호출하면 쿠키에서 `refresh_token`을 읽어 새 토큰을 발급합니다.
- 로그아웃: `/auth/logout` 호출 시 쿠키 삭제(204).
- 운영(HTTPS)에서는 `Secure`가 설정되고, 로컬/테스트 환경에서는 전송 편의를 위해 `Secure`가 비활성화됩니다.

## 주요 엔드포인트 요약
| Tag | 기능 | 비고 |
|-----|------|------|
| auth | 회원가입/로그인/토큰갱신/비밀번호재설정 | 비번 재설정은 이메일 발송 로직 없이 단순 확인 |
| books | 책 생성/검색/상세 | 검색은 부분 문자열 매칭 |
| reviews | 리뷰 CRUD + 요약 | 1인 1책 1리뷰 제한 (중복 400), 응답에 is_my_review/user_book_id 포함 |
| notes/highlights/bookmarks | 독서 중 생성되는 유저 메모/문장/표시 | limit/offset 파라미터 지원 |
| reading | 독서 세션/이벤트 기록 | 종료 시 `total_seconds` 집계 사용 |
| reading-status | 상태 업데이트/요약 | 진행률·총 시간·활동 수 계산, 응답에 user_book_id 포함 |
| taste | 사용자 취향 개요 | 평점 분포 및 태그 추출 |
| support | FAQ (상위 7개 핀), 티켓 생성/조회 | 권한 정책 향후 확장 예정 |
| analytics | 검색/조회 로그 적재 | 조회 로그는 존재하는 책만 허용 (404) |
| meta | 헬스체크 | 배포 모니터링 용도 |

## 에러 & 예시 전략 (v1.1.0 개선)
OpenAPI v1.1.0부터 자동 스크립트(`docs/generate_openapi.py`)가 다음 규칙으로 예시(example)를 삽입합니다:

### 성공 응답 예시
- 스키마 참조(`$ref`)가 있는 2xx/201 응답: 실제 구조 기반 샘플 (예: `UserRead`, `BookDetailResponse`)
- 스키마가 없거나 단순 `{}`인 경우: `{"ok": true}` 기본 값 사용

### 오류 응답 예시
- 400: 존재하지 않으면 자동 추가, `{"detail": "Bad Request"}`
- 404: 존재하지 않으면 자동 추가, `{"detail": "Not Found"}`
- 422: Validation 오류 표준 예시 유지 (`HTTPValidationError` 스키마 + 필드 오류 배열)
- 공통 단일 에러 스키마: `ErrorResponse` (`detail: str`)

### 인증/인가 오류
- 401/403은 FastAPI/HTTPBearer 기본 처리로 별도 example 미삽입 (토큰 누락/잘못된 토큰)

### 엔드포인트 요약 파일
- `docs/endpoint-summary.md`: 메서드·Auth·성공코드·성공예시·400/404/422 예시를 표로 제공 → 프론트 빠른 레퍼런스 용도

### 커스터마이징 방법
1. `SCHEMA_SUCCESS_EXAMPLES` 딕셔너리에 스키마명 추가/수정
2. regenerate: `python docs/generate_openapi.py`
3. 새 예시가 OpenAPI + summary 동시 반영

### 예시 확장 권장 원칙
- 실제 운영 데이터 형태와 충돌되지 않도록 중립적/짧은 값 사용
- 날짜/시간은 ISO8601 (`YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SSZ`) 유지
- 목록 필드는 1~2개 샘플 아이템만 포함
- 문자열은 UI 와이어프레임 테스트 가능한 자연어로 구성

## 에러 응답 패턴 (요약)
- Validation: 422 + `HTTPValidationError` (필드별 상세)
- 일반 비즈니스 오류: 400 + `ErrorResponse` (`{"detail": "메시지"}`)
- 리소스 미존재: 404 + `ErrorResponse`
- 인증 실패: 401 / 권한 문제: 403 (Bearer 처리)

## 프론트 구현 팁
- 페이징: `limit`, `offset` 기본값 (50,0) → 필요 시 작은 값으로 요청하여 첫 페이지 구성
- 리뷰 평점 검증: 스펙에 min=1 max=5 내장 → UI 슬라이더 범위 동일하게 설정
 - 내 리뷰 식별: `GET /reviews/books/{book_id}` 응답의 `is_my_review == true`로 선택. 보조 방법으로 `user_book_id` 저장 후 비교.
 - user_book_id 확보: `POST /reading-status/update`, `GET /reading-status/summary/{book_id}`, `POST /wishlist/` 응답에 포함됨.
  
### 취향 분석(세부 장르 vs 대분류)
- 엔드포인트: `GET /analytics/my-stats`
- 사용 지침:
	- 선호 장르 카드/리스트는 `sub_genres` 배열을 사용하세요.
	- `top_level_genres`는 대분류(소설/시/에세이/만화/웹툰) 표기용입니다.
	- 집계 기준: 평점이 있는 리뷰만 포함합니다(코멘트만은 제외).
	- 정렬: 평균점수(`average_5`)와 편수(`review_count`) 기준 내림차순으로 이미 정렬된 상태로 반환됩니다.
- 다국어 확장 대비: `language` 필드 nullable; 현 단계엔 사용자 표시 생략 가능
- FAQ 7개 핀 제한: 표시 영역 고정 높이 레이아웃에 활용 가능

## 향후 예정 (Roadmap)
- 관리자 권한 분리 (FAQ 작성 제한)
- 외부 책 검색 API 통합 (Google Books 등)
- 알림/푸시(OpenAI, FCM) 연계
- 정렬(`sort`) 파라미터 표준화 및 문서화

## Changelog
- v1 (2025-11-26): 초기 스펙 추출. 코어 기능 + 지원 + 애널리틱스 포함.
- v1.1.0 (2025-11-26): Pydantic V2 ConfigDict 마이그레이션, 스키마 기반 성공 예시, 자동 400/404 삽입, endpoint-summary 확장.
- v1.1.1 (2025-12-04): 리뷰 목록에 `is_my_review` 추가, wishlist/reading-status 응답에 `user_book_id` 포함 명시.

---
문서 수정 시: 버전 파일 복사 → 새 버전명 반영 → `Changelog` Append 후 PR.
