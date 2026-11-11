"""Persist optional rules and monitor new CSV messages independently of the browser."""
import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from watch_filters import filter_rows, validate_settings

KST = dt.timezone(dt.timedelta(hours=9))


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class DesktopSink:
    def __init__(self):
        self.process = None

    def send(self, message):
        if sys.platform != 'win32':
            raise RuntimeError('PC 알림은 Windows에서 사용할 수 있습니다.')
        if self.process is None or self.process.poll() is not None:
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name('desktop_alert.py'))],
                stdin=subprocess.PIPE, text=True, encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()


class WatchService:
    def __init__(self, path, rows_provider, sink=None):
        self.path = Path(path)
        self.rows_provider = rows_provider
        self.sink = sink or DesktopSink()
        self.lock = threading.RLock()
        self.settings = {'desktop_enabled': False, 'rules': []}
        self.error = ''
        try:
            if self.path.exists():
                self.settings = validate_settings(json.loads(self.path.read_text(encoding='utf-8')))
        except (OSError, ValueError, TypeError):
            self.error = '관심조건 설정을 읽지 못했습니다. 조건을 확인하고 다시 저장해 주세요.'
        self.seen = None
        self.stop_event = threading.Event()
        self.thread = None
        self.revision = 0

    def snapshot(self):
        with self.lock:
            return {**json.loads(json.dumps(self.settings)), 'revision': self.revision,
                    'error': self.error, 'monitor_running': bool(self.thread and self.thread.is_alive())}

    def save(self, data):
        settings = validate_settings(data)
        with self.lock:
            if data.get('revision') != self.revision:
                raise ValueError('다른 창에서 조건이 변경됐습니다. 새로고침 후 다시 저장해 주세요.')
            # Baseline on registration/change: historical matches belong in the table only.
            _today, rows = self.rows_provider()
            baseline = {fingerprint(row) for row in rows}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            try:
                temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            self.settings = settings
            self.seen = baseline
            self.revision += 1
            self.error = ''
            return self.snapshot()

    def tick(self):
        with self.lock:
            if not self.settings['desktop_enabled'] or not any(r['enabled'] for r in self.settings['rules']):
                self.seen = None
                return
            today, rows = self.rows_provider()
            keys = {fingerprint(row) for row in rows}
            if self.seen is None:
                self.seen = keys
                return
            fresh = [row for row in rows if fingerprint(row) not in self.seen]
            matches = filter_rows(fresh, self.settings, dt.date.fromisoformat(today))
            if matches:
                # One popup per poll prevents a burst of chat messages from flooding the desktop.
                row = matches[0]
                self.sink.send({'title': f"관심채권 {len(matches)}건 · " + ', '.join(r['name'] for r in row['watch_rules']),
                                'content': row.get('content') or row.get('ticker') or '',
                                'detail': ' · '.join(str(row.get(k) or '') for k in ('timestamp', 'room', 'sender'))})
            self.seen = keys
            self.error = ''

    def test_notification(self):
        with self.lock:
            self.sink.send({'title': 'K-Bond 관심채권 · 테스트 알림',
                            'content': 'PC 왼쪽 하단 알림이 정상적으로 연결되었습니다.',
                            'detail': '테스트 알림 · 실제 채권 메시지가 아닙니다.'})

    def start(self):
        def run():
            while not self.stop_event.wait(2):
                try:
                    self.tick()
                except Exception:
                    logging.exception('Watch notification failed')
                    with self.lock:
                        self.error = 'PC 알림 처리에 실패했습니다. 테스트 알림 또는 실행 창을 확인해 주세요.'
        self.thread = threading.Thread(target=run, name='watch-monitor', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        self.sink.close()
