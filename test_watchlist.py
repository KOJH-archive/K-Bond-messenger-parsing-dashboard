"""Behavioral regression tests; no messenger access or real notifications."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from watch_api import register_watch_api
from watch_filters import add_months, bond_type, date_span, filter_rows, rule_matches, validate_settings, type_alias
from watch_service import WatchService

TODAY = dt.date(2026, 11, 11)


def rule(**values):
    raw = dict(id='one', name='관심조건', keyword='', enabled=True, types=[], maturity_from='',
               maturity_to='', min_months=None, max_months=None)
    raw.update(values)
    return validate_settings({'rules': [raw]})['rules'][0]


def row(content='하나은행 27.08.11 매수', **values):
    data = dict(timestamp='2026-11-11 09:00:00', room='테스트방', sender='테스트', ticker='하나은행',
                maturity='27.08.11', side='매수', content=content)
    data.update(values)
    return data


class FilterTests(unittest.TestCase):
    def test_type_names_filter_the_whole_issuer_matrix(self):
        messages = [
            row('26-2 27.03.01 사자', ticker='26-2'),
            row('29.9.3통 3.5 사자', ticker='29.9.3통'),
            row('중금 27.03.01 매수', ticker='중금'),
            row('신한은행 27.03.01 매수', ticker='신한은행'),
            row('신한카드 27.03.01 매수', ticker='신한카드'),
            row('하나캐피탈 27.03.01 매수', ticker='하나캐피탈'),
            row('삼성전자 77-1 매수', ticker='삼성전자'),
            row('부산도시공사 27.03.01 매수', ticker='부산도시공사'),
            row('신한투자증권 27.03.01 매수', ticker='신한투자증권'),
        ]
        expected = {'국고채':['26-2'], '통안채':['29.9.3통'], '특은채':['중금'],
                    '은행채':['중금','신한은행'], '시중은행채':['신한은행'], '카드채':['신한카드'],
                    '캐피탈채':['하나캐피탈'], '회사채':['삼성전자','신한투자증권']}
        for label, tickers in expected.items():
            with self.subTest(label=label):
                settings = validate_settings({'rules':[rule(name=label)]})
                matches = filter_rows(messages, settings, TODAY)
                self.assertEqual([r['ticker'] for r in matches], tickers)
                self.assertTrue(all(r['watch_types'] for r in matches))

    def test_keyword_type_alias_and_explicit_selection(self):
        self.assertEqual(rule(keyword='은행채')['types'], ['특은','시중은행'])
        self.assertEqual(rule(keyword='은행채')['keyword'], '')
        self.assertEqual(rule(name='카드채', types=['시중은행'])['types'], ['시중은행'])
        self.assertEqual(rule(keyword='은행채', types=['시중은행'])['types'], ['시중은행'])
        self.assertEqual(type_alias('시중 은행채'), ['시중은행'])
        self.assertEqual(rule(name='일반 관심목록', keyword='하나은행')['types'], [])
        with self.assertRaises(ValueError):
            rule(keyword='국고채', types=['카드'])

    def test_bank_and_public_issuers_do_not_leak_into_card_rules(self):
        card = rule(name='카드채')
        bank = row('신한은행 27.03.01 팔자 (카드채 교체 문의)', ticker='신한은행')
        public = row('부산도시공사 27.03.01 팔자', ticker='부산도시공사')
        self.assertFalse(rule_matches(card, bank, TODAY))
        self.assertFalse(rule_matches(card, public, TODAY))
        self.assertFalse(rule_matches(rule(name='은행채'), public, TODAY))
        self.assertFalse(rule_matches(rule(name='회사채'), public, TODAY))

    def test_combined_conditions_and_keywords_or(self):
        r = rule(keyword='하나은행, 신한은행', types=['시중은행'], max_months=9)
        self.assertTrue(rule_matches(r, row(), TODAY))
        self.assertFalse(rule_matches(r, row(maturity='27.08.12'), TODAY))
        self.assertFalse(rule_matches(r, row('현대카드 27.08.11 매수', ticker='현대카드'), TODAY))

    def test_type_only_and_keyword_only_need_no_price(self):
        self.assertTrue(rule_matches(rule(types=['시중은행']), row(maturity=''), TODAY))
        self.assertTrue(rule_matches(rule(keyword='하나'), row(maturity=''), TODAY))

    def test_each_requested_type_and_no_corporate_code_false_positive(self):
        for text, expected in [('국고26-2', '국고'), ('26-2 900 사자', '국고'), ('통안 27.08.11', '통안'),
                               ('29.9.3통 사자', '통안'), ('중금27-1', '특은'), ('산업은행', '특은'),
                               ('하나은행', '시중은행'), ('신한카드123', '카드'), ('한국캐피탈77', '캐피탈'),
                               ('삼성전자 77-1 매수', '회사채'), ('호텔신라 74-2 팔자', '회사채')]:
            with self.subTest(text=text):
                self.assertEqual(bond_type(text), expected)
        self.assertEqual(bond_type('주금공 MBS 26-1 사자'), '')

    def test_month_only_not_used_for_remaining_term(self):
        self.assertFalse(rule_matches(rule(max_months=9), row(maturity='27.08'), TODAY))
        self.assertTrue(rule_matches(rule(maturity_from='2027-08', maturity_to='2027-08'), row(maturity='27.08'), TODAY))
        self.assertFalse(rule_matches(rule(maturity_to='2027-08-10'), row(), TODAY))

    def test_unknown_maturity_and_expired_excluded_from_remaining(self):
        r = rule(max_months=9)
        self.assertFalse(rule_matches(r, row('하나은행 매수', maturity=''), TODAY))
        self.assertFalse(rule_matches(r, row(maturity='26.11.10'), TODAY))

    def test_month_end_and_leap_year(self):
        self.assertEqual(add_months(dt.date(2028, 1, 31), 1), dt.date(2028, 2, 29))
        self.assertEqual(date_span('27.2')[1], dt.date(2027, 2, 28))
        self.assertEqual(date_span('2027년 8월 11일')[0], dt.date(2027, 8, 11))

    def test_no_pairing_across_lines(self):
        message = row('하나은행 27.08.11 매수\n현대카드 27.12.01 매도', maturity='27.08.11')
        self.assertFalse(rule_matches(rule(keyword='하나은행', maturity_from='2027-12'), message, TODAY))
        self.assertTrue(rule_matches(rule(keyword='현대카드', types=['카드'], maturity_from='2027-12'), message, TODAY))

    def test_rules_or_disabled_and_one_result_for_multiple_matches(self):
        settings = validate_settings({'rules':[rule(keyword='하나'), rule(id='two', types=['시중은행'])]})
        result = filter_rows([row()], settings, TODAY)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['watch_rules']), 2)
        settings['rules'][0]['enabled'] = settings['rules'][1]['enabled'] = False
        self.assertEqual(filter_rows([row()], settings, TODAY), [])

    def test_invalid_input_rejected(self):
        for bad in [{}, {'max_months': -1}, {'min_months': 10, 'max_months': 9},
                    {'types':['알수없음']}, {'keyword':'하나', 'maturity_to':'2027-02-30'},
                    {'keyword':'하나', 'maturity_from':'2028-01', 'maturity_to':'2027-01'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rule(**bad)


class FakeSink:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)

    def close(self):
        pass


class DashboardIntegrationTests(unittest.TestCase):
    def test_original_search_recognizes_bond_types_without_literal_keywords(self):
        import dashboard
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
        messages = [row(ticker='하나은행', content='하나은행 사자', timestamp=today+' 09:00:00'),
                    row(ticker='중금', content='중금 사자', timestamp=today+' 09:00:00'),
                    row(ticker='현대카드', content='현대카드 사자', timestamp=today+' 09:00:00'),
                    row(ticker='부산도시공사', content='부산도시공사 사자', timestamp=today+' 09:00:00')]
        with patch.object(dashboard, 'load_collected_messages', return_value=messages):
            client = dashboard.app.test_client()
            self.assertEqual([r['ticker'] for r in client.get('/api/search', query_string={'q':'카드채'}).get_json()['rows']], ['현대카드'])
            self.assertEqual([r['ticker'] for r in client.get('/api/search', query_string={'q':'은행채'}).get_json()['rows']], ['하나은행','중금'])
            self.assertEqual([r['ticker'] for r in client.get('/api/search', query_string={'q':'시중은행채'}).get_json()['rows']], ['하나은행'])

    def test_original_dashboard_preserves_search_and_serves_watch_tab(self):
        import dashboard
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
        message = row(timestamp=today + ' 09:00:00')
        client = dashboard.app.test_client()
        with patch.object(dashboard, 'load_collected_messages', return_value=[message]):
            page = client.get('/')
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'id="chatQuery"', page.data)
            self.assertIn(b'id="watchTab"', page.data)
            for asset in ('watch.js', 'watch.css'):
                with client.get('/static/' + asset) as response:
                    self.assertEqual(response.status_code, 200)
            result = client.get('/api/search?q=하나은행').get_json()
            self.assertEqual(result['total'], 1)
            self.assertEqual(result['rows'][0], message)
            self.assertEqual(client.get('/api/watch/settings').status_code, 200)
            self.assertEqual(client.get('/api/watch/results').status_code, 200)
            self.assertEqual(client.post('/update', json={'type':'ping'}).status_code, 200)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix='watch-test-', dir=workspace)
        if Path(self.temp.name).resolve().parent != workspace:
            raise RuntimeError('Test cleanup path escaped the workspace')
        self.addCleanup(self.temp.cleanup)
        self.rows = [row()]
        self.sink = FakeSink()
        self.service = WatchService(Path(self.temp.name)/'settings.json', lambda:(TODAY.isoformat(), self.rows), self.sink)

    def save(self, **values):
        data = {**self.service.snapshot(), 'rules':[rule(keyword='하나')], 'desktop_enabled':True, **values}
        return self.service.save(data)

    def test_default_off_and_persists_without_affecting_messages(self):
        self.assertFalse(self.service.snapshot()['desktop_enabled'])
        self.save()
        reopened = WatchService(self.service.path, self.service.rows_provider, self.sink)
        self.assertTrue(reopened.settings['desktop_enabled'])
        self.assertEqual(len(self.rows), 1)
        reopened.tick()  # Restart establishes a baseline, not historical alerts.
        self.assertEqual(self.sink.messages, [])

    def test_only_new_messages_once_including_same_second(self):
        self.save()
        self.service.tick()
        self.assertEqual(self.sink.messages, [])
        self.rows.insert(0, row('하나은행 새 매도 3.50'))
        self.service.tick()
        self.service.tick()
        self.assertEqual(len(self.sink.messages), 1)
        self.assertIn('새 매도', self.sink.messages[0]['content'])

    def test_disabled_then_enabled_does_not_replay_and_new_day_works(self):
        self.save(desktop_enabled=False)
        self.rows.insert(0, row('하나은행 과거 추가'))
        self.service.tick()
        self.save()
        self.service.tick()
        self.assertEqual(self.sink.messages, [])
        self.rows[:] = [row('하나은행 익일', timestamp='2026-11-12 00:01:00')]
        self.service.rows_provider = lambda: ('2026-11-12', self.rows)
        self.service.tick()
        self.assertEqual(len(self.sink.messages), 1)

    def test_burst_is_one_popup(self):
        self.save()
        self.rows[:] = [row(f'하나은행 {i}') for i in range(30)]
        self.service.tick()
        self.assertEqual(len(self.sink.messages), 1)
        self.assertIn('30건', self.sink.messages[0]['title'])

    def test_stale_revision_and_failed_save_preserve_state(self):
        old = self.service.snapshot()
        self.save()
        with self.assertRaises(ValueError):
            self.service.save(old)
        with patch('watch_service.os.replace', side_effect=OSError('test')):
            with self.assertRaises(OSError):
                self.save(desktop_enabled=False)
        self.assertTrue(self.service.settings['desktop_enabled'])
        self.assertTrue(json.loads(self.service.path.read_text(encoding='utf-8'))['desktop_enabled'])

    def test_api_filters_before_500_cap_and_ignores_global_search(self):
        self.save()
        self.rows[:] = [row('현대카드', ticker='현대카드') for _ in range(600)] + [row()]
        app = Flask(__name__)
        register_watch_api(app, self.service, self.service.rows_provider)
        client = app.test_client()
        data = client.get('/api/watch/results?q=아무검색').get_json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['rows'][0]['ticker'], '하나은행')
        self.assertEqual(client.get('/api/watch/results?rule=없음').get_json()['rows'], [])
        self.assertEqual(client.put('/api/watch/settings', json={'rules':[]}, headers={'Origin':'https://example.com'}).status_code, 403)
        self.assertEqual(client.put('/api/watch/settings', json={'revision':1,'rules':[{}]}).status_code, 400)
        self.assertEqual(client.put('/api/watch/settings', json=None).status_code, 400)
        self.assertEqual(client.post('/api/watch/test', json={}).status_code, 200)
        self.assertEqual(len(self.sink.messages), 1)

    def test_monitor_recovers_on_notification_failure(self):
        self.save()
        self.rows.insert(0, row('하나은행 신규'))
        with patch.object(self.sink, 'send', side_effect=OSError('test')):
            with self.assertRaises(OSError):
                self.service.tick()
        self.service.tick()
        self.assertEqual(len(self.sink.messages), 1)


if __name__ == '__main__':
    unittest.main()
