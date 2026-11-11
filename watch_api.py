"""Watchlist routes attached to the original dashboard at port 5000."""
import datetime as dt

from flask import jsonify, request

from watch_filters import TYPES, TYPE_ALIASES, filter_rows


def register_watch_api(app, service, rows_provider):
    def same_origin():
        origin = request.headers.get('Origin')
        return not origin or origin == request.host_url.rstrip('/')

    @app.route('/api/watch/settings', methods=['GET', 'PUT'])
    def watch_settings():
        if request.method == 'PUT':
            if not same_origin():
                return jsonify(error='이 대시보드에서 설정을 변경해 주세요.'), 403
            if not request.is_json or (request.content_length and request.content_length > 65536):
                return jsonify(error='설정은 64KB 이하의 JSON이어야 합니다.'), 400
            try:
                return jsonify(service.save(request.get_json()))
            except (ValueError, TypeError) as exc:
                return jsonify(error=str(exc)), 400
            except OSError:
                return jsonify(error='관심조건 저장에 실패했습니다. 저장 폴더를 확인해 주세요.'), 500
        return jsonify(**service.snapshot(), types=TYPES, type_aliases=TYPE_ALIASES)

    @app.get('/api/watch/results')
    def watch_results():
        today, rows = rows_provider()
        settings = service.snapshot()
        matches = filter_rows(rows, settings, dt.date.fromisoformat(today))
        selected = request.args.get('rule', '')
        if selected:
            matches = [row for row in matches if any(r['id'] == selected for r in row['watch_rules'])]
        return jsonify(date=today, total=len(matches), shown=min(500, len(matches)), rows=matches[:500],
                       revision=settings['revision'], desktop_enabled=settings['desktop_enabled'],
                       error=settings['error'], monitor_running=settings['monitor_running'])

    @app.post('/api/watch/test')
    def watch_test():
        if not request.is_json or not same_origin():
            return jsonify(error='대시보드의 테스트 버튼을 사용해 주세요.'), 403
        try:
            service.test_notification()
        except (OSError, RuntimeError) as exc:
            return jsonify(error='PC 알림을 시작하지 못했습니다: ' + str(exc)), 503
        return jsonify(ok=True)
