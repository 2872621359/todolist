"""Vercel WSGI 处理器"""
import json
import os
import time
from threading import Lock
from werkzeug.wrappers import Request, Response
from werkzeug.exceptions import NotFound

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(DIR, 'todo_data.json')
COLLECTIONS = ['tasks', 'lifeEvents', 'habits', 'goals', 'tips']
lock = Lock()


def read_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {c: [] for c in COLLECTIONS}


def write_db(db):
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, DATA_FILE)


def merge_collection(server_items, client_items):
    """Last-write-wins per item id. Returns (merged_list, items_updated_by_client)."""
    index = {it['id']: it for it in server_items}
    changed_ids = set()
    for ci in client_items:
        sid = ci['id']
        existing = index.get(sid)
        if not existing or ci.get('updatedAt', 0) > existing.get('updatedAt', 0):
            index[sid] = ci
            changed_ids.add(sid)
    return list(index.values()), changed_ids


def application(environ, start_response):
    """WSGI 应用"""
    request = Request(environ)
    
    # 处理 CORS
    if request.method == 'OPTIONS':
        response = Response('', status=204)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response(environ, start_response)
    
    # 处理同步接口
    if request.path == '/api/sync' and request.method == 'POST':
        try:
            body = request.get_json()
            client_last_sync = body.get('lastSyncAt', 0)
            client_changes = body.get('changes', {})
            now = int(time.time() * 1000)

            with lock:
                db = read_db()
                response_changes = {}
                for col in COLLECTIONS:
                    server_items = db.get(col, [])
                    client_items = client_changes.get(col, [])
                    merged, changed_ids = merge_collection(server_items, client_items)
                    db[col] = merged
                    response_changes[col] = [
                        it for it in merged
                        if it.get('updatedAt', 0) > client_last_sync and it['id'] not in changed_ids
                    ]
                write_db(db)

            resp_data = {
                'serverTime': now,
                'changes': response_changes
            }
            response = Response(
                json.dumps(resp_data, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response(environ, start_response)
        except Exception as e:
            response = Response(
                json.dumps({'error': str(e)}, ensure_ascii=False),
                status=500,
                mimetype='application/json'
            )
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response(environ, start_response)
    
    # 其他路由返回 404
    response = Response('Not Found', status=404)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response(environ, start_response)
