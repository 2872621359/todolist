"""Vercel Serverless Function — 同步处理器（Vercel KV 持久化）"""
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

COLLECTIONS = ['tasks', 'lifeEvents', 'habits', 'goals', 'tips']
KV_KEY = 'todo_data_v1'

KV_URL = os.environ.get('KV_REST_API_URL', '')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')


def kv_request(path, method='GET', body=None):
    url = f"{KV_URL}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'Bearer {KV_TOKEN}')
    data = None
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        data = body.encode('utf-8') if isinstance(body, str) else body
    with urllib.request.urlopen(req, data=data, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def read_db():
    if not (KV_URL and KV_TOKEN):
        return {c: [] for c in COLLECTIONS}
    try:
        result = kv_request(f'/get/{KV_KEY}')
        value = result.get('result')
        if not value:
            return {c: [] for c in COLLECTIONS}
        return json.loads(value)
    except Exception:
        return {c: [] for c in COLLECTIONS}


def write_db(db):
    if not (KV_URL and KV_TOKEN):
        return
    payload = json.dumps(db, ensure_ascii=False, separators=(',', ':'))
    kv_request(f'/set/{KV_KEY}', method='POST', body=payload)


def merge_collection(server_items, client_items):
    index = {it['id']: it for it in server_items}
    changed_ids = set()
    for ci in client_items:
        sid = ci['id']
        existing = index.get(sid)
        if not existing or ci.get('updatedAt', 0) > existing.get('updatedAt', 0):
            index[sid] = ci
            changed_ids.add(sid)
    return list(index.values()), changed_ids


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, status, payload):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._json(200, {
            'ok': True,
            'kv_configured': bool(KV_URL and KV_TOKEN),
            'kv_url_present': bool(KV_URL),
            'kv_token_present': bool(KV_TOKEN),
            'serverTime': int(time.time() * 1000),
        })

    def do_POST(self):
        try:
            if not (KV_URL and KV_TOKEN):
                self._json(500, {'error': 'Vercel KV not configured. KV_REST_API_URL/TOKEN missing.'})
                return

            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length) if length else b'{}'
            body = json.loads(raw or b'{}')
            client_last_sync = body.get('lastSyncAt', 0)
            client_changes = body.get('changes', {})
            now = int(time.time() * 1000)

            db = read_db()
            response_changes = {}
            changed_any = False
            for col in COLLECTIONS:
                server_items = db.get(col, [])
                client_items = client_changes.get(col, [])
                merged, changed_ids = merge_collection(server_items, client_items)
                if changed_ids:
                    changed_any = True
                db[col] = merged
                response_changes[col] = [
                    it for it in merged
                    if it.get('updatedAt', 0) > client_last_sync and it['id'] not in changed_ids
                ]
            if changed_any:
                write_db(db)

            self._json(200, {'serverTime': now, 'changes': response_changes})
        except Exception as e:
            self._json(500, {'error': str(e), 'type': type(e).__name__})
