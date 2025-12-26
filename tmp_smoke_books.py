import socket, json
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

# Search (without trailing slash)
req=(
  'GET /books/search?q=Test HTTP/1.1\r\n'
  'Host: localhost\r\n'
  '\r\n'
).encode()
resp=send(req)
print('[GET /books/search]')
print(resp.decode(errors='ignore').split('\r\n')[0])
