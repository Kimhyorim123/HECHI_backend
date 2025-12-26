#!/usr/bin/env bash
set -euo pipefail

API="https://api.43-202-101-63.sslip.io"
EMAIL="genre_test_$(date +%s)@example.com"
PASS="Test1234!"

# 1) Register
curl -s -X POST "$API/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"name\":\"Tester\",\"nickname\":\"Tester\",\"password\":\"$PASS\"}" >/dev/null

echo "[OK] Registered: $EMAIL"

# 2) Login
ACCESS=$(curl -s -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | jq -r .access_token)

if [[ -z "$ACCESS" || "$ACCESS" == "null" ]]; then
  echo "[ERROR] Failed to obtain access token" >&2
  exit 1
fi

echo "[OK] Logged in (access token obtained)"

# 3) Upsert reviews for sample books (adjust book IDs if needed)
# These IDs should exist and be mapped to categories like 추리/코미디/가족/SF etc.
# You can edit them based on your DB.
BOOK_IDS=(1501 1502 1510 1515)
RATINGS=(4.5 4.0 4.8 3.9)

for i in "${!BOOK_IDS[@]}"; do
  BID=${BOOK_IDS[$i]}
  RT=${RATINGS[$i]}
  curl -s -X POST "$API/reviews/upsert" \
    -H "Authorization: Bearer $ACCESS" \
    -H 'Content-Type: application/json' \
    -d "{\"book_id\":$BID,\"rating\":$RT}" >/dev/null || true
  echo "[OK] Rated book_id=$BID rating=$RT"
done

# 4) Fetch analytics my-stats
RESP=$(curl -s -X GET "$API/analytics/my-stats" -H "Authorization: Bearer $ACCESS")

# 5) Print top 3 sub_genres and full list snippet
echo "\n===== sub_genres (top3) ====="
echo "$RESP" | jq '.sub_genres | .[:3]'

echo "\n===== sub_genres (all, first 12) ====="
echo "$RESP" | jq '.sub_genres | .[:12]'

echo "\n===== top_level_genres ====="
echo "$RESP" | jq '.top_level_genres'

echo "\n[DONE] Genre stats fetched for $EMAIL"