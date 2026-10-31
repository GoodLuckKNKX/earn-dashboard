#!/usr/bin/env python3
"""Fetch public Earn rates once; keep each exchange's last good snapshot."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STABLE = ['USDT', 'USDC', 'FDUSD', 'USDE', 'USD1', 'TUSD', 'PYUSD', 'RLUSD', 'DAI']
MAJOR = ['BTC', 'ETH', 'SOL']
COINS = STABLE + MAJOR


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def get(url, data=None, headers=None):
    request_headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, data=json.dumps(data).encode() if data is not None else None,
        headers=request_headers,
    )
    # HTTP and JSON errors are caught per exchange, never written with headers/keys.
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def binance():
    out = []
    for coin in COINS:
        d = get('https://www.binance.com/bapi/earn/v1/friendly/finance-earn/simple/product/'
                f'simpleEarnProducts?pageSize=10&current=1&asset={coin}')
        for item in d['data']['list']:
            for p in item['productDetailList']:
                if (p.get('productType') != 'LENDING_FLEXIBLE'
                        or p.get('status') != 'ENABLE' or item['asset'] != coin):
                    continue
                bonus = [(float(t['beginAmount']), float(t['endAmount']), float(t['ratio']) * 100)
                         for t in (p.get('apyTierOption') or [])]
                out.append(dict(ex='Binance', coin=coin, name=p['productId'],
                                type='基础浮动+分档奖励' if bonus else '浮动',
                                base=float(p.get('marketApr') or 0) * 100,
                                bonus=bonus, tiers=None, newuser=False,
                                source='binance.com 公开网页接口 simpleEarnProducts'))
    return out


def okx():
    d = get('https://www.okx.com/api/v5/finance/savings/lending-rate-summary')
    if d.get('code') != '0':
        raise ValueError('OKX rejected request')
    return [dict(ex='OKX', coin=p['ccy'], name='Simple Earn 活期借贷', type='浮动（借贷市场）',
                 base=float(p['estRate']) * 100, bonus=[], tiers=None, newuser=False,
                 source='OKX /api/v5/finance/savings/lending-rate-summary estRate')
            for p in d['data'] if p['ccy'] in COINS]


def gate():
    d = get('https://api.gateio.ws/api/v4/earn/uni/rate')
    return [dict(ex='Gate', coin=p['currency'], name='余币宝 Uni Lending',
                 type='浮动（借贷市场）', base=float(p['est_rate']) * 100,
                 bonus=[], tiers=None, newuser=False,
                 source='Gate /api/v4/earn/uni/rate est_rate')
            for p in d if p['currency'] in COINS]


def bitget():
    out = []
    for coin in COINS:
        d = get('https://www.bitget.com/v1/finance/savings/product/list', {'coinName': coin})
        # The public web endpoint uses 200; the v2 API uses 00000.
        if str(d.get('code')) not in ('200', '00000'):
            raise ValueError('Bitget rejected request')
        for group in d['data'] or []:
            for line in group.get('bizLineProductList', []):
                for p in line.get('productList', []):
                    if (p.get('coinName') != coin or p.get('period') != 0
                            or p.get('periodType') != 1 or p.get('lockModel')
                            or p.get('status') != 2):
                        continue
                    tiers = [(float(t['minStepValue']), float(t['maxStepValue']), float(t['apy']))
                             for t in p['apyList']]
                    newcomer = p.get('annualizedRateType') == 1
                    out.append(dict(ex='Bitget', coin=coin, name='产品' + str(p['id'])[-6:],
                                    type='新用户/限额专享分档（推断）' if newcomer else '交易所设定分档',
                                    base=0, bonus=[], tiers=tiers, newuser=newcomer,
                                    source='bitget.com 公开网页接口 /v1/finance/savings/product/list'))
    return out


def bybit():
    key = os.environ.get('BYBIT_API_KEY', '').strip()
    secret = os.environ.get('BYBIT_API_SECRET', '').strip()
    if bool(key) != bool(secret):
        raise ValueError('BYBIT_API_KEY and BYBIT_API_SECRET must be configured together')
    query = urllib.parse.urlencode({'category': 'FlexibleSaving'})
    headers = {}
    if key and secret:
        timestamp = str(int(time.time() * 1000))
        window = '5000'
        signature = hmac.new(secret.encode(), (timestamp + key + window + query).encode(),
                             hashlib.sha256).hexdigest()
        headers = {'X-BAPI-API-KEY': key, 'X-BAPI-SIGN': signature,
                   'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': window}
    d = get('https://api.bybit.com/v5/earn/product?' + query, headers=headers)
    if d.get('retCode') != 0:
        # Do not persist upstream messages: they can echo authentication information.
        raise ValueError('Bybit rejected request; check credentials, permissions and region')
    out = []
    for p in d['result']['list']:
        if (p.get('category') != 'FlexibleSaving' or p.get('coin') not in COINS
                or p.get('status') != 'Available'):
            continue
        out.append(dict(ex='Bybit', coin=p['coin'], name=str(p['productId']),
                        type='浮动（预估 APR，不含平台奖励）',
                        base=float(p['estimateApr'].removesuffix('%')), bonus=[], tiers=None,
                        newuser=False, source='Bybit /v5/earn/product estimateApr'))
    return out


SOURCES = {'Binance': binance, 'OKX': okx, 'Gate': gate, 'Bitget': bitget, 'Bybit': bybit}


def validate_products(exchange, products):
    if not isinstance(products, list) or not products:
        raise ValueError('No supported products returned; keeping last successful data')
    for p in products:
        if p['ex'] != exchange or p['coin'] not in COINS:
            raise ValueError('Unexpected product identity')
        if not math.isfinite(p['base']) or p['base'] < 0:
            raise ValueError('Invalid base APR')
        if p['tiers'] is not None and not p['tiers']:
            raise ValueError('Empty APR tiers')
        for low, high, rate in (p['tiers'] or []) + p['bonus']:
            if (not all(math.isfinite(n) for n in (low, high, rate))
                    or low < 0 or high <= low or rate < 0):
                raise ValueError('Invalid APR tier')
        for field in ('name', 'type', 'source'):
            if not isinstance(p[field], str):
                raise ValueError('Invalid product text')
    json.dumps(products, allow_nan=False)


def safe_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return f'HTTP {error.code}（接口拒绝、限流或地区限制）'
    if isinstance(error, (TimeoutError, urllib.error.URLError)):
        return '网络连接失败或请求超时'
    if isinstance(error, json.JSONDecodeError):
        return '接口未返回有效 JSON'
    if isinstance(error, ValueError):
        # Only our own fixed messages are public; never serialize unknown exceptions.
        return '接口数据无效，或密钥配置/权限不完整'
    return '接口响应结构异常'


def collect(previous, sources=None):
    sources = SOURCES if sources is None else sources
    checked_at = utc_now()
    products, status = [], {}
    succeeded = False
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {ex: executor.submit(fetch) for ex, fetch in sources.items()}
        for exchange, future in futures.items():
            old_status = previous.get('status', {}).get(exchange, {})
            try:
                current = future.result()
                validate_products(exchange, current)
            except Exception as error:
                current = [p for p in previous.get('products', []) if p['ex'] == exchange]
                last_good = old_status.get('updated_at')
                if not last_good and old_status.get('ok'):
                    last_good = previous.get('updated_at')
                status[exchange] = dict(ok=False, stale=bool(current), n=len(current),
                                        error=safe_error(error), updated_at=last_good,
                                        checked_at=checked_at)
            else:
                succeeded = True
                status[exchange] = dict(ok=True, stale=False, n=len(current), error=None,
                                        updated_at=checked_at, checked_at=checked_at)
            products.extend(current)
            print(f'{exchange}: {"ok" if status[exchange]["ok"] else "error"}, '
                  f'{len(current)} products, stale={status[exchange]["stale"]}')
    return dict(schema_version=1, updated_at=checked_at if succeeded else previous.get('updated_at'),
                checked_at=checked_at, stable=STABLE, major=MAJOR, products=products, status=status)


def read_previous(path):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    # Bootstrap only: retain the project's original dated snapshot on the first run.
    seed = ROOT / 'snapshot.json'
    if not seed.exists():
        return {}
    data = json.loads(seed.read_text(encoding='utf-8'))
    stamp = data.get('updated')
    data['updated_at'] = (datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
                          .replace(tzinfo=timezone(timedelta(hours=8)))
                          .astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')) if stamp else None
    for state in data.get('status', {}).values():
        state['updated_at'] = data['updated_at'] if state.get('ok') else None
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'rates.json')
    args = parser.parse_args()
    data = collect(read_previous(args.output))
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(args.output)
    print(f'Wrote {args.output} ({len(data["products"])} products); updated_at={data["updated_at"]}')


if __name__ == '__main__':
    main()
