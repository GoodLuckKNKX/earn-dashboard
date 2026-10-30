import os
import json, threading, time, urllib.request, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
STABLE=['USDT','USDC','FDUSD','USDE','USD1','TUSD','PYUSD','RLUSD','DAI']
MAJOR=['BTC','ETH','SOL']
COINS=STABLE+MAJOR
UA={'User-Agent':'Mozilla/5.0','Content-Type':'application/json'}
def get(url,data=None):
    r=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,headers=UA)
    return json.load(urllib.request.urlopen(r,timeout=20))
# tier: list of (min,max,apr%) ; product: dict(ex,coin,name,type,tiers,base,newuser,source)
def binance():
    out=[]
    for c in COINS:
        d=get(f'https://www.binance.com/bapi/earn/v1/friendly/finance-earn/simple/product/simpleEarnProducts?pageSize=10&current=1&asset={c}')
        for it in d['data']['list']:
            for p in it['productDetailList']:
                if p.get('productType')!='LENDING_FLEXIBLE' or p.get('status')!='ENABLE' or it['asset']!=c: continue
                base=float(p.get('marketApr') or 0)*100
                tiers=[(float(t['beginAmount']),float(t['endAmount']),float(t['ratio'])*100) for t in (p.get('apyTierOption') or [])]
                out.append(dict(ex='Binance',coin=c,name=p['productId'],type='基础浮动+分档奖励' if tiers else '浮动',base=base,bonus=tiers,tiers=None,newuser=False,
                    source='binance.com 公开网页接口 simpleEarnProducts'))
    return out
def okx():
    d=get('https://www.okx.com/api/v5/finance/savings/lending-rate-summary')['data']
    return [dict(ex='OKX',coin=x['ccy'],name='Simple Earn 活期借贷',type='浮动（借贷市场）',base=float(x['estRate'])*100,bonus=[],tiers=None,newuser=False,
        source=f"OKX /api/v5/finance/savings/lending-rate-summary estRate（上期 {float(x['preRate'])*100:.2f}%）") for x in d if x['ccy'] in COINS]
def gate():
    d=get('https://api.gateio.ws/api/v4/earn/uni/rate')
    return [dict(ex='Gate',coin=x['currency'],name='余币宝 Uni Lending',type='浮动（借贷市场）',base=float(x['est_rate'])*100,bonus=[],tiers=None,newuser=False,
        source='Gate /api/v4/earn/uni/rate est_rate') for x in d if x['currency'] in COINS]
def bitget():
    out=[]
    for c in COINS:
        d=get('https://www.bitget.com/v1/finance/savings/product/list',{'coinName':c})['data']
        for g in d or []:
            for b in g.get('bizLineProductList',[]):
                for p in b.get('productList',[]):
                    if p.get('coinName')!=c or p.get('period')!=0 or p.get('periodType')!=1 or p.get('lockModel') or p.get('status')!=2: continue
                    tiers=[(float(a['minStepValue']),float(a['maxStepValue']),float(a['apy'])) for a in p['apyList']]
                    nu=p.get('annualizedRateType')==1
                    out.append(dict(ex='Bitget',coin=c,name='产品'+p['id'][-6:],type=('新用户/限额专享分档（推断）' if nu else '交易所设定分档'),base=0,bonus=[],tiers=tiers,newuser=nu,
                        source='bitget.com 公开网页接口 /v1/finance/savings/product/list'))
    return out
def bybit():
    get('https://api.bybit.com/v5/earn/product?category=FlexibleSaving&coin=USDT'); return []
SRC={'Binance':binance,'OKX':okx,'Bitget':bitget,'Bybit':bybit,'Gate':gate}
STATE={'products':[],'status':{},'updated':None}
def poll():
    while True:
        prods=[];st={}
        for k,f in SRC.items():
            try:
                r=f();prods+=r;st[k]={'ok':True,'n':len(r)}
            except Exception as e:
                msg=str(e)
                if k=='Bybit': msg='Bybit 公开接口被 CloudFront 按服务器所在地区拦截（403），且其活期产品接口需 API Key，无法获取'
                st[k]={'ok':False,'err':msg[:200]}
        STATE.update(products=prods,status=st,updated=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'))
        time.sleep(60)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/data'):
            b=json.dumps(dict(STATE,stable=STABLE,major=MAJOR),ensure_ascii=False).encode();ct='application/json'
        else:
            b=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'index.html'),'rb').read();ct='text/html; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',ct);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
    def log_message(self,*a):pass
threading.Thread(target=poll,daemon=True).start()
import os
ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8787'))),H).serve_forever()
