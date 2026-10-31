import copy
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SPEC = importlib.util.spec_from_file_location(
    'fetch_rates', Path(__file__).resolve().parents[1] / 'scripts' / 'fetch_rates.py')
rates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rates)


def product(exchange, base=3.5):
    return dict(ex=exchange, coin='USDT', name='fixture', type='浮动', base=base,
                bonus=[], tiers=None, newuser=False, source='fixture')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.previous = dict(updated_at='2026-10-30T11:22:00Z',
                             products=[product('Binance'), product('OKX')],
                             status={'Binance': dict(ok=True, updated_at='2026-10-30T11:00:00Z'),
                                     'OKX': dict(ok=True, updated_at='2026-10-30T11:22:00Z')})

    @staticmethod
    def fail():
        raise urllib.error.HTTPError('https://example.test', 403, 'Forbidden', {}, None)

    def test_failed_exchange_keeps_its_old_products_and_timestamp(self):
        original = copy.deepcopy(self.previous)
        result = rates.collect(self.previous, {'Binance': self.fail, 'OKX': lambda: [product('OKX', 6)]})
        self.assertEqual(result['products'], [product('Binance'), product('OKX', 6)])
        self.assertTrue(result['status']['Binance']['stale'])
        self.assertFalse(result['status']['Binance']['ok'])
        self.assertEqual(result['status']['Binance']['updated_at'], '2026-10-30T11:00:00Z')
        self.assertIn('403', result['status']['Binance']['error'])
        self.assertEqual(self.previous, original)
        self.assertTrue(result['updated_at'].endswith('Z'))

    def test_repeated_total_failure_does_not_make_old_data_look_fresh(self):
        sources = {'Binance': self.fail, 'OKX': self.fail}
        first = rates.collect(self.previous, sources)
        second = rates.collect(first, sources)
        self.assertEqual(second['products'], self.previous['products'])
        self.assertEqual(second['updated_at'], self.previous['updated_at'])
        self.assertEqual(second['status']['Binance']['updated_at'], '2026-10-30T11:00:00Z')

    def test_first_run_without_history_survives_total_failure(self):
        result = rates.collect({}, {'Bybit': self.fail})
        self.assertEqual(result['products'], [])
        self.assertIsNone(result['updated_at'])
        self.assertFalse(result['status']['Bybit']['stale'])

    def test_invalid_or_empty_response_keeps_last_good_data(self):
        for output in ([], [product('Binance', float('nan'))], [product('Binance', -1)]):
            with self.subTest(output=output):
                result = rates.collect(self.previous, {'Binance': lambda: output})
                self.assertEqual(result['products'], [product('Binance')])
                self.assertFalse(result['status']['Binance']['ok'])

    def test_success_clears_stale_and_error(self):
        previous = rates.collect(self.previous, {'Binance': self.fail})
        result = rates.collect(previous, {'Binance': lambda: [product('Binance', 5)]})
        self.assertTrue(result['status']['Binance']['ok'])
        self.assertFalse(result['status']['Binance']['stale'])
        self.assertIsNone(result['status']['Binance']['error'])

    def test_bootstrap_converts_original_beijing_timestamp_to_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'snapshot.json').write_text(json.dumps(dict(
                updated='2026-10-30 19:22:00', products=[], status={'OKX': {'ok': True}})))
            with patch.object(rates, 'ROOT', root):
                previous = rates.read_previous(root / 'data' / 'rates.json')
            self.assertEqual(previous['updated_at'], '2026-10-30T11:22:00Z')
            self.assertEqual(previous['status']['OKX']['updated_at'], previous['updated_at'])


class SourceTests(unittest.TestCase):
    @patch.dict(os.environ, {'BYBIT_API_KEY': 'fixture-key', 'BYBIT_API_SECRET': 'fixture-secret'})
    @patch.object(rates.time, 'time', return_value=1234)
    def test_bybit_signing_and_percent_units(self, _clock):
        body = {'retCode': 0, 'result': {'list': [dict(category='FlexibleSaving', coin='USDT',
                status='Available', estimateApr='4.25%', productId='1'),
                dict(category='OnChain', coin='ETH', status='Available', estimateApr='99%', productId='2')]}}
        with patch.object(rates, 'get', return_value=body) as get:
            products = rates.bybit()
        headers = get.call_args.kwargs['headers']
        expected = hmac.new(b'fixture-secret', b'1234000fixture-key5000category=FlexibleSaving',
                            hashlib.sha256).hexdigest()
        self.assertEqual(headers['X-BAPI-SIGN'], expected)
        self.assertEqual(headers['X-BAPI-API-KEY'], 'fixture-key')
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['base'], 4.25)
        self.assertNotIn('fixture-key', json.dumps(products))
        self.assertNotIn('fixture-secret', json.dumps(products))

    @patch.dict(os.environ, {'BYBIT_API_KEY': '', 'BYBIT_API_SECRET': ''})
    def test_bybit_without_secrets_uses_public_endpoint(self):
        with patch.object(rates, 'get', return_value={'retCode': 0, 'result': {'list': []}}) as get:
            self.assertEqual(rates.bybit(), [])
        self.assertEqual(get.call_args.kwargs['headers'], {})

    @patch.dict(os.environ, {'BYBIT_API_KEY': 'fixture-key', 'BYBIT_API_SECRET': ''})
    def test_incomplete_bybit_secrets_are_isolated_and_not_exposed(self):
        with patch.object(rates, 'get') as get:
            result = rates.collect({}, {'Bybit': rates.bybit})
        get.assert_not_called()
        self.assertFalse(result['status']['Bybit']['ok'])
        self.assertNotIn('fixture-key', json.dumps(result))

    def test_upstream_error_cannot_leak_credentials(self):
        def fail():
            raise RuntimeError('fixture-secret echoed by upstream')
        result = rates.collect({}, {'Bybit': fail})
        self.assertNotIn('fixture-secret', json.dumps(result))

    def test_bitget_public_success_code_and_tiers(self):
        body = {'code': '200', 'data': [{'bizLineProductList': [{'productList': [dict(
            coinName='USDT', period=0, periodType=1, lockModel=False, status=2,
            id='123456789', annualizedRateType=0,
            apyList=[dict(minStepValue='0', maxStepValue='300000', apy='5.5')])]}]}]}
        with patch.object(rates, 'COINS', ['USDT']), patch.object(rates, 'get', return_value=body):
            products = rates.bitget()
        self.assertEqual(products[0]['tiers'], [(0, 300000, 5.5)])
        rates.validate_products('Bitget', products)


if __name__ == '__main__':
    unittest.main()
