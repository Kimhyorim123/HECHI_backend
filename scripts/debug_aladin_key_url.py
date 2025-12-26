import os
import requests

key = os.getenv("ALADIN_API_KEY")
print("KEY repr:", repr(key))

url = (
    "http://www.aladin.co.kr/ttb/api/ItemList.aspx"
    f"?ttbkey={key}"
    "&QueryType=Bestseller"
    "&MaxResults=5"
    "&start=1"
    "&SearchTarget=Book"
    "&output=js"
    "&Version=20131101"
)
print("REQUEST URL:", url)

resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
print("STATUS:", resp.status_code)
print("RAW TEXT:", resp.text[:500])
