import socket, json, time
HOST='localhost'; PORT=8000

def send(req: bytes) -> bytes:
    s=socket.socket(); s.connect((HOST,PORT)); s.send(req)
    chunks=[]
    while True:
        c=s.recv(65536)
        if not c: break
        chunks.append(c)
        if len(b''.join(chunks))>2_000_000: break
    s.close()
    return b''.join(chunks)

def status(resp: bytes) -> str:
    return resp.decode(errors='ignore').split('\r\n')[0]

def body(resp: bytes) -> bytes:
    return resp.split(b'\r\n\r\n',1)[1]

def json_body(resp: bytes):
    try:
        return json.loads(body(resp).decode())
    except Exception:
        return None

email=f"test{int(time.time())}@example.com"
password="P@ssw0rd123"

# Register
reg_body=json.dumps({"email":email,"password":password,"name":"Tester","nickname":"Tester"})
req=(
  'POST /auth/register HTTP/1.1\r\n'
  'Host: localhost\r\n'
  'Content-Type: application/json\r\n'
  f'Content-Length: {len(reg_body)}\r\n'
  '\r\n'
  + reg_body
).encode()
resp=send(req)
print('[POST /auth/register]', status(resp))

# Login
login_body=json.dumps({"email":email,"password":password})
req=(
  'POST /auth/login HTTP/1.1\r\n'
  'Host: localhost\r\n'
  'Content-Type: application/json\r\n'
  f'Content-Length: {len(login_body)}\r\n'
  '\r\n'
  + login_body
).encode()
resp=send(req)
print('[POST /auth/login]', status(resp))
login_json=json_body(resp) or {}
access=login_json.get('access_token') or login_json.get('access') or ''
print('access len:', len(access))

# Create book with Authorization
book=json.dumps({
  'isbn':'978-0-123456-47-2',
  'title':'Test Book',
  'publisher':'Test Pub',
  'category':'Fiction',
  'total_pages':300,
  'thumbnail':'http://example.com/cover.jpg',
  'small_thumbnail':'http://example.com/cover-small.jpg',
  'google_rating':4.2,
  'google_ratings_count':128
})
req=(
  'POST /books/ HTTP/1.1\r\n'
  'Host: localhost\r\n'
  'Content-Type: application/json\r\n'
  f'Authorization: Bearer {access}\r\n'
  f'Content-Length: {len(book)}\r\n'
  '\r\n'
  + book
).encode()
resp=send(req)
print('[POST /books/]', status(resp))
print('create body head:', body(resp)[:120])

# Search
req=(
  'GET /books/?q=Test&limit=10 HTTP/1.1\r\n'
  'Host: localhost\r\n'
  '\r\n'
).encode()
resp=send(req)
print('[GET /books/search]', status(resp))
print('search body head:', body(resp)[:120])
