"""Vercel WSGI 处理器 — 使用 Vercel KV (Upstash Redis) 持久化"""
import json
import os
import time
import urllib.request
import urllib.error
from threading import Lock
from werkzeug.wrappers import Request, Response

COLLECTIONS = ['tasks', 'lifeEvents', 'habits', 'goals', 'tips']
KV_KEY = 'todo_data_v1'
lock = Lock()

# Vercel KV 自动注入的环境变量
KV_URL = os.environ.get('KV_REST_API_URL', '')
KV_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')


def kv_request(path, method='GET', body=None):
    """调用 Vercel KV REST API"""
    url = f"{KV_URL}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'Bearer {KV_TOKEN}')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        data = body if isinstance(body, bytes) else body.encode('utf-8')
    else:
        data = None
    with urllib.request.urlopen(req, data=data, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def read_db():
    """从 KV 读取数据"""
    if not KV_URL or not KV_TOKEN:
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
    """写入 KV"""
    if not KV_URL or not KV_TOKEN:
        return
    payload = json.dumps(db, ensure_ascii=False, separators=(',', ':'))
    kv_request(f'/set/{KV_KEY}', method='POST', body=payload)


def merge_collection(server_items, client_items):
    """每条记录用 updatedAt 做最终胜出合并"""
    index = {it['id']: it for it in server_items}
    changed_ids = set()
    for ci in client_items:
        sid = ci['id']
        existing = index.get(sid)
        if not existing or ci.get('updatedAt', 0) > existing.get('updatedAt', 0):
            index[sid] = ci
            changed_ids.add(sid)
    return list(index.values()), changed_ids


def cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def application(environ, start_response):
    request = Request(environ)

    if request.method == 'OPTIONS':
        return cors_headers(Response('', status=204))(environ, start_response)

    # GET /api/sync —— 健康检查
    if request.path == '/api/sync' and request.method == 'GET':
        info = {
            'ok': True,
            'kv_configured': bool(KV_URL and KV_TOKEN),
            'serverTime': int(time.time() * 1000),
        }
        resp = Response(json.dumps(info), status=200, mimetype='application/json')
        return cors_headers(resp)(environ, start_response)

    if request.path == '/api/sync' and request.method == 'POST':
        try:
            if not KV_URL or not KV_TOKEN:
                resp = Response(
                    json.dumps({'error': 'Vercel KV not configured. Set KV_REST_API_URL and KV_REST_API_TOKEN.'}),
                    status=500, mimetype='application/json'
                )
                return cors_headers(resp)(environ, start_response)

            body = request.get_json()
            client_last_sync = body.get('lastSyncAt', 0)
            client_changes = body.get('changes', {})
            now = int(time.time() * 1000)

            with lock:
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

            resp_data = {'serverTime': now, 'changes': response_changes}
            resp = Response(
                json.dumps(resp_data, ensure_ascii=False),
                status=200, mimetype='application/json'
            )
            return cors_headers(resp)(environ, start_response)
        except Exception as e:
            resp = Response(
                json.dumps({'error': str(e)}, ensure_ascii=False),
                status=500, mimetype='application/json'
            )
            return cors_headers(resp)(environ, start_response)

    resp = Response('Not Found', status=404)
    return cors_headers(resp)(environ, start_response)


if __name__ == '__main__':
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application)
