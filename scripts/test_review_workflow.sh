#!/usr/bin/env bash
set -euo pipefail

API_URL="http://api:8000"
if curl -fsS "https://api.43-202-101-63.sslip.io/health" >/dev/null 2>&1; then
  API_URL="https://api.43-202-101-63.sslip.io"
fi

email="demo_user_$$@example.com"
pw="pass1234"

echo "[1/5] register (ignore errors if exists)"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API_URL/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$pw\",\"name\":\"Demo\"}"

echo "[2/5] login"
TOKENS=$(curl -fsS -X POST "$API_URL/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$pw\",\"remember_me\":true}")
ACCESS=$(echo "$TOKENS" | python - <<'PY'
import sys, json
print(json.load(sys.stdin)['access_token'])
PY
)

# pick a book id that exists
BOOK_ID=$(curl -fsS "$API_URL/search?q=the" | python - <<'PY'
import sys, json
items=json.load(sys.stdin).get('items',[])
print(items[0]['id'] if items else 1477)
PY
)

echo "[3/5] wishlist add"
WL=$(curl -fsS -X POST "$API_URL/wishlist/?book_id=$BOOK_ID" -H "Authorization: Bearer $ACCESS")
echo "$WL"
UB_ID=$(echo "$WL" | python - <<'PY'
import sys, json
j=json.load(sys.stdin)
print(j.get('user_book_id') or '')
PY
)

if [ -z "$UB_ID" ]; then
  echo "no user_book_id from wishlist, updating reading-status"
  RS=$(curl -fsS -X POST "$API_URL/reading-status/update" -H 'Content-Type: application/json' -H "Authorization: Bearer $ACCESS" \
    -d "{\"book_id\":$BOOK_ID,\"status\":\"READING\"}")
  echo "$RS"
  UB_ID=$(echo "$RS" | python - <<'PY'
import sys, json
print(json.load(sys.stdin).get('user_book_id') or '')
PY
)
fi

echo "[4/5] upsert my review"
REV=$(curl -fsS -X POST "$API_URL/reviews/upsert" -H 'Content-Type: application/json' -H "Authorization: Bearer $ACCESS" \
  -d "{\"book_id\":$BOOK_ID,\"rating\":4.0,\"content\":\"좋았어요\"}")
echo "$REV"

echo "[5/5] list reviews with is_my_review"
LIST=$(curl -fsS "$API_URL/reviews/books/$BOOK_ID" -H "Authorization: Bearer $ACCESS")
python - <<'PY'
import sys, json
arr=json.load(sys.stdin)
mine=[x for x in arr if x.get('is_my_review')]
print('my review count:', len(mine))
print('first my review:', mine[0] if mine else None)
PY
