# BookStopper Backend (FastAPI)

종이책 독서 데이터(시간·페이지·이벤트)를 수집하고 AI 요약/추천과 푸시 알림을 제공하는 백엔드 + 워커 서비스입니다.

## 구성 개요
- **FastAPI API 서버**: 인증/JWT, 사용자·도서·독서 세션·이벤트·메모·AI Job·알림 CRUD & 트리거
- **Worker 프로세스**: AIJob(OpenAI 호출) / Notification(FCM 발송) 지연 태스크 처리 (DB 폴링)
- **DB**: 초기 SQLite → Docker 환경에서 MySQL로 전환 예정 (단일 소스 오브 트루스)
- **외부 서비스**: Google Books(or 국내 API), OpenAI, Firebase Cloud Messaging

## 디렉터리 구조
```
app/
  main.py          # FastAPI 진입점 (라우터/CORS)
  database.py      # SQLAlchemy Engine & SessionLocal
  models.py        # ORM 모델 (User, Book, ReadingSession 등)
  core/
    config.py      # 환경변수 Settings (Pydantic)
    security.py    # 패스워드 해시/JWT 유틸
  api/
    auth.py        # 인증 라우터
  schemas/         # Pydantic DTO 모음
  repositories/    # (향후) DB 접근 추상화
  services/        # (향후) 비즈니스 로직 계층
worker/
  worker.py        # AIJob/Notification 폴링 스켈레톤
requirements.txt
README.md
```

## 빠른 시작 (로컬 개발)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (임시) 테이블 생성: Alembic 적용 전 단계
python -c "from app.models import Base; from app.database import engine; Base.metadata.create_all(bind=engine)"

uvicorn app.main:app --reload --port 8000  # API 서버
python -m worker.worker                    # Worker (별도 터미널)
```

## 환경변수 (.env 예시)
```
ENVIRONMENT=local
SECRET_KEY=CHANGE_ME_TO_LONG_RANDOM_STRING
DATABASE_URL=sqlite:///./dev.db
CORS_ORIGINS=*
OPENAI_API_KEY=sk-xxx                # 선택: AI 요약/추천
FCM_SERVICE_ACCOUNT_JSON_PATH=/path/to/service_account.json  # 선택: FCM 발송
ACCESS_TOKEN_EXP_MINUTES=30          # (settings에서 기본 제공)
REFRESH_TOKEN_EXP_DAYS=14
```

## 기본 엔드포인트
- GET /health               : 헬스 체크
- POST /auth/register       : 회원가입
- POST /auth/login          : 로그인 (Access/Refresh 발급)
- POST /auth/refresh        : Refresh로 토큰 재발급
- GET /auth/me              : 현재 사용자 조회 (임시 token 파라미터 → Bearer 헤더로 개선 예정)

## 모델 주요 개념 (추가 포함)
- Device: BookStopper BLE 디바이스 등록
- ReadingSession / ReadingEvent: 세션 단위 / 세부 이벤트 추적
- FCMToken: 다중 기기 FCM 토큰 저장
- AIJob: 비동기 AI 작업 큐 (요약/추천 등)
- Notification: 사용자 알림 기록

## 로드맵 (단계적 개선)
| 단계 | 작업 | 설명 |
|------|------|------|
| 1 | Authorization 헤더 처리 | Bearer 파싱 dependency 작성, /auth/me 개선 |
| 2 | Alembic 초기화 | 마이그레이션 도구 도입, 첫 revision 생성 |
| 3 | Docker Compose | api, worker, db(MySQL), (선택 nginx) 구성 |
| 4 | 테스트(Pytest) | Auth happy path + 실패 케이스 작성 |
| 5 | Refresh 회전 전략 | 이전 Refresh 무효화(세션/블랙리스트) 도입 |
| 6 | ReadingSession API | 세션 시작/이벤트/종료 엔드포인트 구현 |
| 7 | OpenAI 통합 | Worker에서 프롬프트 생성 & 결과 저장 |
| 8 | FCM 발송 구현 | 실제 HTTP v1 API 호출 + 토큰 비활성화 처리 |
| 9 | 로깅/모니터링 | 구조화 로그(JSON) + metrics 초석 |
| 10 | Async 전환 | 외부 I/O 증가 시 async SQLAlchemy 도입 |

## Alembic (예정)
초기에는 `metadata.create_all()` 방식. 마이그레이션 도입 시:
```bash
alembic init migrations
# env.py에서 Settings.database_url 주입
alembic revision --autogenerate -m "init"
alembic upgrade head
```

## 주의 & 향후 개선
- SECRET_KEY 반드시 교체 & 커밋 금지
- Refresh 토큰 회전/무효화 전략 미구현 → 보안 강화 필요
- Worker: 재시도(backoff), Graceful shutdown, 구조화 로깅 미구현
- User.fcm_token vs FCMToken 테이블 중 장기적으로 FCMToken만 유지 권장
- OpenAI/FCM 통합 시 키 관리 (환경변수/AWS SSM) 적용

## 간단 cURL 예시
```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"a@test.com","password":"secret","name":"Alice","nickname":"alice"}'

curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"a@test.com","password":"secret"}'
```

## 라이선스
추후 결정 (예: MIT / Apache-2.0). 현재는 내부 사용.

---
이 문서는 MVP 단계에서 점진적으로 업데이트됩니다. 개선 제안은 Issue/PR로 관리 예정.
