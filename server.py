#!/usr/bin/env python3
"""四象限待办 – 同步服务器
仅依赖 Python 标准库。同时提供静态文件和 /api/sync 同步接口。
数据持久化为同目录下的 todo_data.json。
"""
import json, os, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DIR, 'todo_data.json')
COLLECTIONS = ['tasks', 'lifeEvents', 'habits', 'goals', 'tips']
lock = threading.Lock()


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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    def do_GET(self):
        if self.path == '/':
            self.path = '/todo.html'
        super().do_GET()

    def do_POST(self):
        if self.path != '/api/sync':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.requestline and self.rfile.read(length))
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
                # Return items the client doesn't have yet
                # (updated on server since client's last sync, excluding what client just sent)
                response_changes[col] = [
                    it for it in merged
                    if it.get('updatedAt', 0) > client_last_sync and it['id'] not in changed_ids
                ]
            write_db(db)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({
            'serverTime': now,
            'changes': response_changes
        }, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        if args and '/api/sync' in str(args[0]):
            return
        super().log_message(fmt, *args)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 9099))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'🌸 四象限待办同步服务器启动: http://0.0.0.0:{port}')
    print(f'   数据文件: {DATA_FILE}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 已停止')
