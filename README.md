# Bookstopper Backend

Bookstopper 애플리케이션의 백엔드 서비스입니다.

## 기술 스택
- FastAPI
- MySQL
- Docker Compose
- Nginx
- Background Worker
- OpenAI / Firebase / Aladin API 연동

## GitHub에 포함할 파일
다음 파일들은 GitHub에 올려야 나중에 같은 상태로 복원할 수 있습니다.
- `app/` 아래의 애플리케이션 코드
- `worker/` 아래의 백그라운드 워커 코드
- `migrations/versions/` 아래의 데이터베이스 마이그레이션
- `docker-compose.yml`
- `Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.nginx`
- `nginx/nginx.conf`
- `requirements.txt`
- `README.md`
- `.env.example`
- `docs/openapi-v1.1.json`

GitHub에 올리면 안 되는 파일은 다음과 같습니다.
- `.env`
- Firebase 서비스 계정 JSON
- 실제 API 키 / 비밀번호
- `uploads/` 아래의 로컬 업로드 파일
- 의도적으로 보관하는 경우를 제외한 DB 덤프 파일

## 최초 설정
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd bookstopper-backend
cp .env.example .env
```

컨테이너를 실행하기 전에 `.env` 안의 실제 값을 반드시 채우세요. 특히 DB 비밀번호, API 키, Firebase JSON 호스트 경로를 확인해야 합니다.

## Docker Compose 실행
```bash
docker compose up -d --build
```

## 컨테이너 중지
```bash
docker compose down
```

## 마이그레이션 적용
수동으로 마이그레이션을 실행해야 하는 경우:

```bash
docker compose exec api alembic upgrade head
```

이미 실행 중인 서버에서 컨테이너 이름이 고정돼 있다면 아래 명령도 사용할 수 있습니다.

```bash
docker exec -it bookstopper-api alembic upgrade head
```

## pull 이후 복원 절차
같은 서버든 새 서버든, 저장소를 다시 받았을 때의 최소 복원 절차는 다음과 같습니다.

```bash
git pull origin main
cp .env.example .env   # .env가 없을 때만
# 실제 환경값 입력

docker compose up -d --build
docker compose exec api alembic upgrade head
```

Firebase 서비스 계정 파일을 저장소 밖에 두는 경우에는 `.env`의 `FCM_SERVICE_ACCOUNT_JSON_HOST_PATH`를 해당 호스트 경로로 지정하고, `FCM_SERVICE_ACCOUNT_JSON_PATH`는 컨테이너 내부 경로로 유지하세요.

## 코드 백업과 서비스 백업은 다릅니다
GitHub에는 코드가 저장되지만, 실제 서비스 상태까지 자동으로 복원되지는 않습니다.
정확한 복원을 위해서는 다음도 별도로 필요합니다.
- DB 백업
- 업로드 파일 백업
- 실제 `.env` 값
- Firebase 자격 증명 파일

## DB 백업
MySQL 덤프 생성:

```bash
docker exec bookstopper-db mysqldump -u bookstopper -p'YOUR_DB_PASSWORD' bookstopper > backup_bookstopper.sql
```

복원:

```bash
docker exec -i bookstopper-db mysql -u bookstopper -p'YOUR_DB_PASSWORD' bookstopper < backup_bookstopper.sql
```

## 업로드 파일 백업
현재 프로젝트는 로컬 파일 업로드를 사용합니다. S3를 사용하지 않는 경우 업로드 파일도 따로 백업해야 합니다.

백업 생성:

```bash
tar -czf uploads_backup.tar.gz uploads/
```

복원:

```bash
tar -xzf uploads_backup.tar.gz
```

## 권장 백업 세트
실제로 복구 가능한 상태로 보관하려면 아래 항목을 함께 관리하세요.
- GitHub 저장소
- GitHub 밖에 안전하게 보관한 `.env`
- GitHub 밖에 안전하게 보관한 Firebase admin SDK JSON
- `backup_bookstopper.sql`
- `uploads_backup.tar.gz`

## 현재 업로드 방식
- 그룹 이미지와 프로필 이미지는 `/uploads/presign`을 사용할 수 있습니다.
- S3가 설정되지 않으면 업로드는 로컬 저장소로 fallback 됩니다.
- 로컬 업로드 파일은 `/static/uploads/` 경로로 제공됩니다.

## API 문서
커밋된 OpenAPI 사양:
- `docs/openapi-v1.1.json`
