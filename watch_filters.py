"""Optional watch rules. Existing category/parser rules are deliberately untouched."""
import calendar
import datetime as dt
import re

TYPES = ('국고', '통안', '특은', '시중은행', '카드', '캐피탈', '회사채')
TYPE_ALIASES = {
    '국고': ['국고'], '국고채': ['국고'], '국채': ['국고'],
    '통안': ['통안'], '통안채': ['통안'],
    '특은': ['특은'], '특은채': ['특은'], '특수은행채': ['특은'],
    '은행채': ['특은', '시중은행'], '시중은행': ['시중은행'], '시중은행채': ['시중은행'],
    '카드': ['카드'], '카드채': ['카드'], '캐피탈': ['캐피탈'], '캐피탈채': ['캐피탈'],
    '회사채': ['회사채'],
}
OUTSIDE_TYPES = re.compile(r'공사|공단|도시개발|지역개발|주금공|한국전력|한전|한수원|\bLH\b|\bMBS\b|\bFRN\b|전단채|ABCP|ABSTB|\bCP\b|\bCD\b|금융지주', re.I)
DATE = re.compile(r'(?<![\d.])(\d{4}|\d{2})\s*(?:[./-]|년\s*)\s*(\d{1,2})(?:\s*(?:[./-]|월\s*)\s*(\d{1,2}))?(?:일|월)?(?!\d)')


def type_alias(value):
    return list(TYPE_ALIASES.get(re.sub(r'\s+', '', str(value)), []))


def date_span(value):
    """Dates without a day stay a month interval; never invent a maturity day."""
    match = DATE.fullmatch(str(value).strip())
    if not match:
        raise ValueError('만기는 YYYY-MM-DD 또는 YYYY-MM 형식으로 입력해 주세요.')
    year, month, day = match.groups()
    year = int(year) + (2000 if len(year) == 2 else 0)
    month = int(month)
    try:
        start = dt.date(year, month, int(day) if day else 1)
        end = start if day else start.replace(day=calendar.monthrange(year, month)[1])
    except ValueError as exc:
        raise ValueError('유효한 만기일을 입력해 주세요.') from exc
    return start, end


def add_months(day, months):
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def bond_type(text, category=''):
    if OUTSIDE_TYPES.search(text):
        return ''
    # Specific issuers precede broad financial names (e.g. 신한카드/신한은행).
    if re.search(r'카드', text, re.I):
        return '카드'
    if re.search(r'캐피탈|커머셜|할부금융', text, re.I):
        return '캐피탈'
    if re.search(r'산금|산업은행|중금|중소기업은행|기업은행|수은|수출입은행|특은', text):
        return '특은'
    if re.search(r'통안|(?<![가-힣])(?:구구삼통|구삼통|삼통|구구통|구통|통당)(?![가-힣])|\d{2}\.\d{1,2}\.\d{1,2}\s*통', text):
        return '통안'
    if re.search(r'국고|국채|물가채|^\s*\d{2}-\d{1,2}(?![\w-])', text):
        return '국고'
    if re.search(r'증권|금융투자', text):
        return '회사채'
    if re.search(r'은행|국민|신한|우리|하나|농협|수협|부산|대구|경남|전북|광주|제주|SC제일|씨티|카카오뱅크|케이뱅크|토스뱅크', text):
        return '시중은행'
    if category == '회사채':
        return '회사채'
    if not category and not re.search(r'MBS|FRN|공사|공단|한전|LH|주금공|전단채|ABCP|ABSTB|\bCP\b|\bCD\b|금융지주', text, re.I):
        if re.search(r'[가-힣A-Za-z]{2,}.*(?:\d|팔자|사자|매수|매도)|회사채', text):
            return '회사채'
    return ''


def line_bond_type(row, line, single_line=True):
    if single_line:
        ticker = str(row.get('ticker') or '').strip()
        if ticker:
            # An issuer parsed into ticker takes priority over broker signatures or commentary.
            if OUTSIDE_TYPES.search(ticker):
                return ''
            kind = bond_type(ticker)
            if kind:
                return kind
    return bond_type(line, row.get('category', ''))


def row_bond_types(row):
    lines = [line.strip() for line in str(row.get('content') or '').splitlines() if line.strip()] or ['']
    return list(dict.fromkeys(kind for line in lines if (kind := line_bond_type(row, line, len(lines) == 1))))


def validate_settings(data):
    if not isinstance(data, dict) or not isinstance(data.get('desktop_enabled', False), bool):
        raise ValueError('잘못된 관심조건 설정입니다.')
    rules = data.get('rules', [])
    if not isinstance(rules, list) or len(rules) > 50:
        raise ValueError('관심조건은 최대 50개까지 등록할 수 있습니다.')
    clean, ids = [], set()
    for raw in rules:
        if not isinstance(raw, dict):
            raise ValueError('잘못된 관심조건입니다.')
        rule = {key: str(raw.get(key, '')).strip() for key in ('id', 'name', 'keyword', 'maturity_from', 'maturity_to')}
        if not rule['id'] or len(rule['id']) > 80 or rule['id'] in ids:
            raise ValueError('관심조건 ID가 올바르지 않습니다.')
        ids.add(rule['id'])
        if len(rule['keyword']) > 200 or len(rule['name']) > 80:
            raise ValueError('조건 이름은 80자, 키워드는 200자 이내로 입력해 주세요.')
        rule['name'] = rule['name'] or rule['keyword'] or '관심조건'
        rule['types'] = raw.get('types', [])
        if not isinstance(rule['types'], list) or any(t not in TYPES for t in rule['types']):
            raise ValueError('지원하지 않는 채권종류입니다.')
        rule['types'] = list(dict.fromkeys(rule['types']))
        keyword_types = type_alias(rule['keyword'])
        if keyword_types:
            selected = [kind for kind in rule['types'] if kind in keyword_types] if rule['types'] else keyword_types
            if not selected:
                raise ValueError('키워드의 채권종류와 선택한 채권종류가 다릅니다. 조건을 확인해 주세요.')
            rule['types'], rule['keyword'] = selected, ''
        elif not rule['types']:
            # Exact, recognized type names are an explicit type request; other labels stay labels.
            rule['types'] = type_alias(rule['name'])
        rule['enabled'] = raw.get('enabled', True)
        if not isinstance(rule['enabled'], bool):
            raise ValueError('활성화 값이 올바르지 않습니다.')
        for field in ('min_months', 'max_months'):
            value = raw.get(field)
            if value in ('', None):
                rule[field] = None
            elif isinstance(value, bool) or not re.fullmatch(r'\d{1,3}', str(value)) or int(value) > 600:
                raise ValueError('잔존만기는 0~600 사이의 정수 개월로 입력해 주세요.')
            else:
                rule[field] = int(value)
        if all(rule[field] is not None for field in ('min_months', 'max_months')) and rule['min_months'] > rule['max_months']:
            raise ValueError('최소 잔존만기는 최대보다 클 수 없습니다.')
        for field in ('maturity_from', 'maturity_to'):
            if rule[field]:
                date_span(rule[field])
        if rule['maturity_from'] and rule['maturity_to'] and date_span(rule['maturity_from'])[0] > date_span(rule['maturity_to'])[1]:
            raise ValueError('만기 시작일은 종료일보다 늦을 수 없습니다.')
        if not (rule['keyword'].strip(', ') or rule['types'] or rule['maturity_from'] or rule['maturity_to'] or rule['min_months'] is not None or rule['max_months'] is not None):
            raise ValueError('키워드, 만기, 채권종류 중 하나 이상을 입력해 주세요.')
        clean.append(rule)
    return {'desktop_enabled': data.get('desktop_enabled', False), 'rules': clean}


def rule_matches(rule, row, today):
    if not rule['enabled']:
        return False
    lines = [line.strip() for line in str(row.get('content') or '').splitlines() if line.strip()] or ['']
    keywords = [k.strip().casefold() for k in rule['keyword'].split(',') if k.strip()]
    lower = date_span(rule['maturity_from'])[0] if rule['maturity_from'] else None
    upper = date_span(rule['maturity_to'])[1] if rule['maturity_to'] else None
    needs_remaining = rule['min_months'] is not None or rule['max_months'] is not None
    for line in lines:
        # Multiline orders are evaluated per line to avoid pairing one issuer with another maturity.
        text = f"{row.get('ticker', '')} {line}" if len(lines) == 1 else line
        if keywords and not any(k in text.casefold() for k in keywords):
            continue
        if rule['types'] and line_bond_type(row, line, len(lines) == 1) not in rule['types']:
            continue
        if not (lower or upper or needs_remaining):
            return True
        maturity_text = (row.get('maturity') or line) if len(lines) == 1 else line
        for match in DATE.finditer(maturity_text):
            try:
                start, end = date_span(match.group())
            except ValueError:
                continue
            if lower and start < lower or upper and end > upper:
                continue
            if needs_remaining:
                # A month-only maturity cannot establish the remaining term accurately.
                if start != end or start < today:
                    continue
                if rule['min_months'] is not None and start < add_months(today, rule['min_months']):
                    continue
                if rule['max_months'] is not None and start > add_months(today, rule['max_months']):
                    continue
            return True
    return False


def filter_rows(rows, settings, today):
    result = []
    for row in rows:
        matched = [rule for rule in settings['rules'] if rule_matches(rule, row, today)]
        if matched:
            result.append({**row, 'watch_types': row_bond_types(row),
                           'watch_rules': [{'id': r['id'], 'name': r['name']} for r in matched]})
    return result
