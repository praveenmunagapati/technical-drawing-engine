import urllib.request
import urllib.parse
import json
import uuid

boundary = uuid.uuid4().hex
data = []
data.append(f'--{boundary}')
data.append('Content-Disposition: form-data; name="file"; filename="test.svg"')
data.append('Content-Type: image/svg+xml')
data.append('')
data.append('<svg></svg>')
data.append(f'--{boundary}--')
data.append('')
body = '\r\n'.join(data).encode('utf-8')

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/jobs/upload?page=A1&auto_scale=true',
    data=body,
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)
try:
    resp = urllib.request.urlopen(req)
    print(resp.status, resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode('utf-8'))
