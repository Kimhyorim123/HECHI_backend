# Google Books Import 사용 가이드

## 개요
내장된 `/books/import/google` 엔드포인트를 통해 개별 ISBN 또는 키워드(query) 기반으로 Google Books API 결과를 DB에 저장할 수 있습니다. 썸네일은 원본 URL 문자열로 저장되며 클라이언트(앱/웹)에서 직접 로딩합니다.

## 엔드포인트
- `POST /books/import/google`
  - Request Body: `{ "isbn": "<ISBN13 또는 ISBN10>" }` 또는 `{ "query": "검색어" }` (둘 중 하나 필수)
  - Response: `GoogleImportResult { created[], updated[], skipped[] }`

## 필드 매핑 규칙
| Google 원본 | 내부 Book 필드 | 비고 |
|-------------|----------------|------|
| volumeInfo.title | title | 필수 없으면 skip |
| industryIdentifiers | isbn | ISBN_13 > ISBN_10 우선 |
| volumeInfo.publisher | publisher | 없으면 NULL |
| volumeInfo.publishedDate | published_date | YYYY->1/1, YYYY-MM->해당월 1일, YYYY-MM-DD 그대로 |
| volumeInfo.language | language | ISO 639-1 예상 |
| volumeInfo.categories[0] | category | 첫 항목만 사용 |
| volumeInfo.pageCount | total_pages | int |
| volumeInfo.authors | authors (중간 테이블) | 소문자 normalize 후 중복 방지 |
| volumeInfo.imageLinks.thumbnail | thumbnail | 원본 URL |
| volumeInfo.imageLinks.smallThumbnail | small_thumbnail | 원본 URL |
| volumeInfo.averageRating | google_rating | float |
| volumeInfo.ratingsCount | google_ratings_count | int |

## 중복 처리
- 동일 ISBN 존재 시: 썸네일 / 평점 관련 필드만 갱신 (`updated[]` 목록에 포함) + `skipped[]` 에 ISBN 추가.
- ISBN 없는 결과: 현재 로직은 ISBN 없더라도 저장 시도하지 않음 (title 없으면 skip). 필요 시 정책 변경 가능.

## 대량 수집 전략
1. **ISBN 목록 기반**: 명확한 대상(추천 리스트 등)이 있을 때 안정적. 중복 최소.
2. **Query 기반**: `query` 사용 시 기본 최대 5권(`maxResults` 내부 기본값). 확장 필요 시 서비스 레벨에서 pagination 추가 (`startIndex` 활용) 개선 가능.
3. **초기 시드 추천**: 카테고리/언어별 10~30권 정도로 시작 → 앱 기능/UX 확인 후 확장.
4. **결측치 처리**: 썸네일 없으면 클라이언트에서 placeholder 이미지 제공.

## 쿼터 / 제한 (Google Books API)
- 공식 하드 리밋 문서화는 상세치가 적으며 일반적 사용은 무료로 상당히 관대함.
- 실무 운영 팁:
  - 연속 빠른 다량 요청 시 429 또는 일시 실패 가능 → 100~200ms sleep 권장.
  - 한 번에 수천 권 이상 적재 시 캐싱 계층(예: Redis) 또는 배치 워커 사용 고려.
  - 비즈니스 로직상 동일 ISBN 재조회는 import 엔드포인트 대신 내부 DB 검색 활용.

## 향후 확장 아이디어
- `startIndex` + `maxResults` 파라미터 지원하는 확장 엔드포인트 (`/books/import/google/search`)
- ISBN 없는 결과 제외 명시 옵션 (`exclude_no_isbn=true`)
- 저자/카테고리 정규화 파이프라인 별도 모듈화
- 썸네일 프록시/캐시 (이미지 만료 및 속도 최적화 목적)

## 신규 확장 엔드포인트 (배치 수집)
- `POST /books/import/google/query`
  - Body 예시:
    ```json
    {
      "query": "machine learning",
      "pages": 3,
      "page_size": 30,
      "language": "en",
      "max_create": 70,
      "exclude_no_isbn": true
    }
    ```
  - 동작: `startIndex` 를 자동 증가시키며 페이지 반복 수집. `max_create` 초과 시 즉시 중단.
  - 언어 필터: `language` 지정 시 해당 `volumeInfo.language` 가 정확히 일치하는 항목만 저장.
  - ISBN 없는 항목은 기본적으로 제외.

### 대량 한국어(KO) 도서 수집 예시
```bash
TOKEN=...; API_BASE=https://api.43-202-101-63.sslip.io
curl -X POST $API_BASE/books/import/google/query \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"베스트셀러", "pages":5, "page_size":40, "language":"ko", "max_create":150}' | jq '.created | length'
```

추천 한국어 키워드 조합:
- "베스트셀러", "추천 도서", "자기계발", "경영", "심리학", "IT", "프로그래밍", "데이터 분석", "클라우드", "AI", "소설", "에세이", "인문학"

반복 스크립트 예시:
```bash
QUERIES=("베스트셀러" "자기계발" "프로그래밍" "데이터 분석" "AI" "소설")
for q in "${QUERIES[@]}"; do
  curl -s -X POST $API_BASE/books/import/google/query \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"query":"'"$q"'","pages":3,"page_size":40,"language":"ko","exclude_no_isbn":true}' \
    | jq -r '.created[]?.isbn'
  sleep 0.2
done
```

### 베스트셀러 ISBN 기반 (권장 정확성 높음)
가능하면 신뢰 소스(서점 순위)에서 ISBN 목록 추출 후 아래 형태로 배치:
```bash
while read -r isbn; do
  curl -s -X POST $API_BASE/books/import/google \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"isbn":"'"$isbn"'"}' | jq -r '.created[]?.title'
  sleep 0.15
done < bestsellers_isbn_ko.txt
```

### 수천 권 확장 시 권장
1. ISBN 우선(정확한 중복 제어) → Query 보완
2. 실패/429 재시도 로직 포함한 간단 워커(백오프: 0.2s, 0.4s, 0.8s)
3. 중간 진행 상황 로그 + 에러 로그 분리
4. 주기적 스냅샷: 총 레코드 수 / 저자 수 / 카테고리 분포

### 운영 체크 포인트
- 평균 요청 성공/실패 비율 모니터링 (추후 metrics 테이블 도입 가능)
- 썸네일 404 발생률 (캐시/프록시 고려 지표)
- ISBN 중복율 (Query 기반 수집 범위 재조정 판단 근거)


## 사용 예시
```bash
# ISBN 단일 수집
curl -X POST $API_BASE/books/import/google \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"isbn":"9780134853987"}' | jq

# 키워드 기반 5권 수집 (기본값)
curl -X POST $API_BASE/books/import/google \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"data science"}' | jq
```

## 간단 배치 스크립트 예시
`seed_isbns.txt` 에 ISBN 목록 준비 후:
```bash
while read -r isbn; do
  [[ -z "$isbn" ]] && continue
  curl -s -X POST $API_BASE/books/import/google \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"isbn":"'"$isbn"'"}' | jq -r '.created[]?.isbn'
done < seed_isbns.txt
```

## 에러/실패 대응
| 상황 | 원인 | 대응 |
|------|------|------|
| 400 isbn 또는 query 없음 | 요청 바디 누락 | 요청 JSON 수정 |
| 401 Unauthorized | 토큰 누락/만료 | 재로그인 후 토큰 갱신 |
| 429 Too Many Requests | 과도한 연속 요청 | 지연(Sleep) 추가 후 재시도 |
| 5xx Google API 오류 | 외부 서비스 불안정 | 지수적 백오프 재시도 |

## 체크리스트
- `.env` 에 `GOOGLE_BOOKS_API_KEY` 존재 여부 확인
- 첫 임포트 후 DB에 `thumbnail` URL 저장 여부 확인
- 중복 ISBN 재수집 시 `updated[]` 항목 포함 확인
- 클라이언트 썸네일 placeholder 정상 처리

---
필요 시 pagination 확장 또는 워커 기반 대량 수집 구현 도와드릴 수 있습니다.
