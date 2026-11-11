from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
import csv
import datetime
import os
import re
from pathlib import Path

from watch_api import register_watch_api
from watch_service import WatchService
from run_integrated import source_revision
from watch_filters import type_alias, row_bond_types

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kbond_secret_key'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
RUNTIME_REVISION = source_revision()
socketio = SocketIO(app, cors_allowed_origins="*")

_message_cache = {"signature": None, "rows": []}


def _clean_excel_text(value):
    value = (value or "").strip()
    if value.startswith('="') and value.endswith('"'):
        return value[2:-1]
    return value


def _room_from_filename(filename):
    return "[채권] 막무가내" if "막무가내" in filename else "[채권] 블커본드"


def load_collected_messages():
    """수집 CSV 전체를 읽되 파일이 바뀌지 않았으면 메모리 캐시를 재사용합니다."""
    files = []
    for filename in os.listdir(os.path.dirname(os.path.abspath(__file__))):
        if filename.startswith("kbond_messages_") and filename.endswith(".csv"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            try:
                stat = os.stat(path)
                files.append((path, stat.st_mtime_ns, stat.st_size))
            except OSError:
                continue

    signature = tuple(sorted(files))
    if signature == _message_cache["signature"]:
        return _message_cache["rows"]

    rows = []
    for path, _, _ in sorted(files):
        room = _room_from_filename(os.path.basename(path))
        try:
            with open(path, encoding="utf-8-sig", newline="") as csv_file:
                for row in csv.DictReader(csv_file):
                    timestamp = (row.get("수집시간") or "").strip()
                    if not timestamp:
                        continue
                    rows.append({
                        "timestamp": timestamp,
                        "room": room,
                        "sender": (row.get("송신자") or "").strip(),
                        "ticker": _clean_excel_text(row.get("종목")),
                        "maturity": _clean_excel_text(row.get("만기")),
                        "side": (row.get("구분") or "").strip(),
                        "content": (row.get("대화내용") or "").strip(),
                    })
        except (OSError, UnicodeError, csv.Error):
            continue

    rows.sort(key=lambda item: item["timestamp"], reverse=True)
    _message_cache["signature"] = signature
    _message_cache["rows"] = rows
    return rows


def _search_terms(query):
    stopwords = {
        "채권", "정보", "내역", "검색", "조회", "찾아줘", "찾아", "보여줘", "보여",
        "알려줘", "알려", "관련", "대한", "들어간", "있는", "것", "거", "좀", "해줘",
    }
    tokens = re.findall(r"[0-9A-Za-z가-힣.+-]+", query.lower())
    return [token for token in tokens if token not in stopwords and len(token) >= 2]


def watch_today_rows():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()
    return today, [row for row in load_collected_messages() if row['timestamp'][:10] == today]


watch_service = WatchService(Path(__file__).resolve().parent / 'data' / 'watch_settings.json', watch_today_rows)
register_watch_api(app, watch_service, watch_today_rows)

@app.route('/')
def index():
    return render_template('index.html', runtime_revision=RUNTIME_REVISION[:10])


@app.route('/api/health')
def health():
    response = jsonify(app='kbond-integrated', watchlist=True, revision=RUNTIME_REVISION,
                       instance=os.environ.get('KBOND_INSTANCE_TOKEN', ''), pid=os.getpid())
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.after_request
def refresh_page_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/search')
def search_messages():
    query = (request.args.get("q") or "").strip()
    terms = _search_terms(query)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    today = now.strftime("%Y-%m-%d")
    rows = [
        row for row in load_collected_messages()
        if row["timestamp"][:10] == today
    ]

    if query and not terms:
        return jsonify({
            "query": query,
            "terms": [],
            "total": 0,
            "shown": 0,
            "rows": [],
            "answer": "기관명, 종목명, 송신자, 매수·매도 같은 검색어를 입력해 주세요.",
            "date": today,
            "as_of": now.strftime("%Y-%m-%d %H:%M:%S"),
        })

    requested_types = type_alias(query)
    if requested_types:
        filtered = [row for row in rows if set(row_bond_types(row)).intersection(requested_types)]
    elif terms:
        filtered = []
        for row in rows:
            searchable = " ".join(str(value).lower() for value in row.values())
            if all(term in searchable for term in terms):
                filtered.append(row)
    else:
        filtered = rows

    total = len(filtered)
    shown = filtered[:500]
    if query:
        answer = f"오늘 ‘{query}’ 조건으로 {total:,}건을 찾았습니다. 최신 수집 건부터 보여드릴게요."
    else:
        answer = f"오늘 수집된 내역은 {total:,}건입니다. 검색어로 필요한 채권만 빠르게 찾아보세요."

    return jsonify({
        "query": query,
        "terms": terms,
        "total": total,
        "shown": len(shown),
        "rows": shown,
        "answer": answer,
        "date": today,
        "as_of": now.strftime("%Y-%m-%d %H:%M:%S"),
    })

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    if not data: return "No data", 400
    
    # 핑 메시지는 처리하지 않고 응답만 함
    if data.get("type") == "ping":
        return "pong", 200
        
    socketio.emit('new_message', data)
    return "OK", 200

if __name__ == '__main__':
    print("Dashboard server starting at http://localhost:5000")
    watch_service.start()
    try:
        socketio.run(app, host='127.0.0.1', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    finally:
        watch_service.stop()
