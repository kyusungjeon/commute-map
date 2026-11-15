#!/usr/bin/env python3
"""수도권 아파트 실거래가(매매·전세)를 받아 법정동별 중위가격 prices.js 를 만든다.

- 자료: 공공데이터포털 '국토교통부_아파트 매매 실거래가 자료', '국토교통부_아파트 전월세 실거래가 자료'
- 동 위치: 그 동에서 거래가 가장 많은 단지의 지번을 네이버 Geocoding 으로 한 번만 찾아 data/geo_cache.json 에 저장
- 필요한 환경변수: MOLIT_KEY, NAVER_ID, NAVER_SECRET  (GitHub Secrets 에만 넣는다. 저장소에 쓰지 않는다)
- 개별 거래는 저장소에 남기지 않고 동 단위 통계만 내보낸다.
"""
import os,sys,json,time,datetime,statistics,urllib.request,urllib.parse,urllib.error
import xml.etree.ElementTree as ET

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE=os.path.join(ROOT,'.cache','molit'); GEO=os.path.join(ROOT,'data','geo_cache.json')
MONTHS=int(os.environ.get('MONTHS','12')); GEO_MAX=int(os.environ.get('GEO_MAX','800') or 800)
BANDS=[40,60,85]            # 전용면적 경계: ≤40, 40~60, 60~85, 85 초과
MIN_N=3                     # 거래가 이보다 적으면 값을 비운다

SGG={ # 법정동코드 앞 5자리: (시도, 시군구)
'11110':('서울특별시','종로구'),'11140':('서울특별시','중구'),'11170':('서울특별시','용산구'),'11200':('서울특별시','성동구'),'11215':('서울특별시','광진구'),'11230':('서울특별시','동대문구'),'11260':('서울특별시','중랑구'),'11290':('서울특별시','성북구'),'11305':('서울특별시','강북구'),'11320':('서울특별시','도봉구'),'11350':('서울특별시','노원구'),'11380':('서울특별시','은평구'),'11410':('서울특별시','서대문구'),'11440':('서울특별시','마포구'),'11470':('서울특별시','양천구'),'11500':('서울특별시','강서구'),'11530':('서울특별시','구로구'),'11545':('서울특별시','금천구'),'11560':('서울특별시','영등포구'),'11590':('서울특별시','동작구'),'11620':('서울특별시','관악구'),'11650':('서울특별시','서초구'),'11680':('서울특별시','강남구'),'11710':('서울특별시','송파구'),'11740':('서울특별시','강동구'),
'28110':('인천광역시','중구'),'28140':('인천광역시','동구'),'28177':('인천광역시','미추홀구'),'28185':('인천광역시','연수구'),'28200':('인천광역시','남동구'),'28237':('인천광역시','부평구'),'28245':('인천광역시','계양구'),'28260':('인천광역시','서구'),'28710':('인천광역시','강화군'),
'41111':('경기도','수원시 장안구'),'41113':('경기도','수원시 권선구'),'41115':('경기도','수원시 팔달구'),'41117':('경기도','수원시 영통구'),'41131':('경기도','성남시 수정구'),'41133':('경기도','성남시 중원구'),'41135':('경기도','성남시 분당구'),'41150':('경기도','의정부시'),'41171':('경기도','안양시 만안구'),'41173':('경기도','안양시 동안구'),'41190':('경기도','부천시'),'41210':('경기도','광명시'),'41220':('경기도','평택시'),'41250':('경기도','동두천시'),'41271':('경기도','안산시 상록구'),'41273':('경기도','안산시 단원구'),'41281':('경기도','고양시 덕양구'),'41285':('경기도','고양시 일산동구'),'41287':('경기도','고양시 일산서구'),'41290':('경기도','과천시'),'41310':('경기도','구리시'),'41360':('경기도','남양주시'),'41370':('경기도','오산시'),'41390':('경기도','시흥시'),'41410':('경기도','군포시'),'41430':('경기도','의왕시'),'41450':('경기도','하남시'),'41461':('경기도','용인시 처인구'),'41463':('경기도','용인시 기흥구'),'41465':('경기도','용인시 수지구'),'41480':('경기도','파주시'),'41500':('경기도','이천시'),'41550':('경기도','안성시'),'41570':('경기도','김포시'),'41590':('경기도','화성시'),'41610':('경기도','광주시'),'41630':('경기도','양주시'),'41650':('경기도','포천시'),'41670':('경기도','여주시'),'41800':('경기도','연천군'),'41820':('경기도','가평군'),'41830':('경기도','양평군'),
}
# 행정구역 개편으로 코드가 바뀌었을 수 있는 곳. 최근 달에 거래가 있으면 쓰고 없으면 건너뛴다.
PROBE={'41192':('경기도','부천시 원미구'),'41194':('경기도','부천시 소사구'),'41196':('경기도','부천시 오정구'),
       '41591':('경기도','화성시'),'41593':('경기도','화성시'),'41595':('경기도','화성시'),'41597':('경기도','화성시')}
API={'sale':'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade',
     'rent':'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent'}

class ApiStop(Exception):pass

def months(n,today=None):
    d=(today or datetime.date.today()).replace(day=1);out=[]
    for _ in range(n):
        out.append(d.strftime('%Y%m'));d=(d-datetime.timedelta(days=1)).replace(day=1)
    return out

def num(t):
    try:return float(str(t).replace(',','').strip())
    except Exception:return None

def parse(kind,xml):
    """응답 XML → (rows, totalCount). row = [동, 전용면적, 금액(만원), 단지명, 지번]"""
    try:root=ET.fromstring(xml)
    except ET.ParseError:raise ApiStop('XML 아님: '+xml[:200])
    code=root.findtext('.//resultCode')
    if code is None or code.strip() not in('00','000'):
        raise ApiStop((root.findtext('.//returnAuthMsg') or root.findtext('.//resultMsg') or xml[:200]).strip())
    rows=[]
    for it in root.iter('item'):
        g=lambda k:(it.findtext(k) or '').strip()
        dong,area=g('umdNm'),num(g('excluUseAr'))
        if not dong or not area:continue
        if kind=='sale':
            if g('cdealType'):continue                     # 계약 해제 건 제외
            amt=num(g('dealAmount'))
        else:
            if (num(g('monthlyRent')) or 0)>0:continue      # 월세 제외, 전세만
            amt=num(g('deposit'))
        if not amt:continue
        rows.append([dong,area,amt,g('aptNm'),g('jibun')])
    return rows,int(num(root.findtext('.//totalCount')) or 0)

def http(url,headers=None,tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers or {}),timeout=40) as r:return r.read().decode('utf-8','replace')
        except urllib.error.HTTPError as e:
            if e.code in(401,403,429):raise ApiStop(f'HTTP {e.code}')
            last=e
        except Exception as e:last=e
        time.sleep(2*(k+1))
    raise ApiStop(f'연결 실패: {last}')

def fetch(kind,code,ym,key):
    rows,page=[],1
    while True:
        xml=http(f"{API[kind]}?serviceKey={key}&LAWD_CD={code}&DEAL_YMD={ym}&pageNo={page}&numOfRows=1000")
        r,total=parse(kind,xml);rows+=r
        if page*1000>=total:break
        page+=1
    return rows

def collect(key,today=None):
    os.makedirs(CACHE,exist_ok=True)
    ms=months(MONTHS,today);fresh=set(ms[:2]);stopped=None;data={};codes=dict(SGG)
    try:
        for c,nm in PROBE.items():
            if fetch('sale',c,ms[1],key):codes[c]=nm;print('개편 코드 사용:',c,nm)
    except ApiStop as e:stopped=str(e)
    for kind in('sale','rent'):
        for ym in ms:                                   # 최근 달부터
            for code in codes:
                f=os.path.join(CACHE,f'{kind}_{code}_{ym}.json')
                if os.path.exists(f) and (ym not in fresh or stopped):
                    data[(kind,code,ym)]=json.load(open(f));continue
                if stopped:continue
                try:
                    rows=fetch(kind,code,ym,key);json.dump(rows,open(f,'w'),ensure_ascii=False);data[(kind,code,ym)]=rows
                except ApiStop as e:
                    stopped=str(e);print('!! 호출 중단:',stopped)
                    if os.path.exists(f):data[(kind,code,ym)]=json.load(open(f))
    return data,codes,ms,stopped

def band(a):return sum(a>b for b in BANDS)

def aggregate(data):
    """→ {(code,동): {'s':[4 lists],'j':[4 lists],'cx':{(단지,지번):건수}}}"""
    out={}
    for (kind,code,ym),rows in data.items():
        for dong,area,amt,apt,jibun in rows:
            d=out.setdefault((code,dong),{'s':[[],[],[],[]],'j':[[],[],[],[]],'cx':{}})
            d['s' if kind=='sale' else 'j'][band(area)].append(amt)
            if jibun:d['cx'][(apt,jibun)]=d['cx'].get((apt,jibun),0)+1
    return out

def geocode(q,nid,sec):
    hdr={'x-ncp-apigw-api-key-id':nid,'x-ncp-apigw-api-key':sec}
    for base in('https://maps.apigw.ntruss.com/map-geocode/v2/geocode','https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode'):
        try:
            j=json.loads(http(base+'?query='+urllib.parse.quote(q),hdr,tries=1));a=(j.get('addresses') or [])
            return [round(float(a[0]['y']),5),round(float(a[0]['x']),5)] if a else None
        except ApiStop as e:err=e
    raise err

def locate(agg,codes,nid,sec):
    geo=json.load(open(GEO)) if os.path.exists(GEO) else {}
    used=0;stopped=None
    for (code,dong),d in sorted(agg.items(),key=lambda kv:-sum(kv[1]['cx'].values())):
        k=f'{code}|{dong}'
        if k in geo or not d['cx'] or stopped:continue
        if used>=GEO_MAX:break
        (apt,jibun),_=max(d['cx'].items(),key=lambda kv:kv[1]);sido,sgg=codes[code]
        try:
            pt=geocode(f'{sido} {sgg} {dong} {jibun}',nid,sec);used+=1
            geo[k]=pt or geocode(f'{sido} {sgg} {dong}',nid,sec) or []
            if not pt:used+=1
            time.sleep(0.05)
        except ApiStop as e:stopped=str(e);print('!! 주소 찾기 중단:',stopped)
    os.makedirs(os.path.dirname(GEO),exist_ok=True)
    json.dump(geo,open(GEO,'w'),ensure_ascii=False,sort_keys=True,indent=0)
    return geo,used,stopped

def med(v):return str(int(round(statistics.median(v)))) if len(v)>=MIN_N else ''

def build(agg,codes,geo,ms,complete):
    lines=[]
    for (code,dong),d in sorted(agg.items()):
        pt=geo.get(f'{code}|{dong}')
        if not pt:continue
        s=[med(x) for x in d['s']];j=[med(x) for x in d['j']]
        if not any(s+j):continue
        lines.append(f"{codes[code][1]} {dong}|{pt[0]},{pt[1]}|{','.join(s)}|{','.join(j)}")
    period=f"{ms[-1][:4]}년 {int(ms[-1][4:])}월~{ms[0][:4]}년 {int(ms[0][4:])}월"
    js=("// 수도권 아파트 실거래가 동별 중위가격(만원). tools/fetch_prices.py 가 만든다. 출처: 국토교통부 실거래가 공개자료\n"
        "// 형식: 시군구 동|위도,경도|매매(≤40,40~60,60~85,85초과)|전세(같은 순서). 거래 "+str(MIN_N)+"건 미만은 빈칸\n"
        f'window.PRICES={{period:"{period}",made:"{datetime.date.today().isoformat()}",complete:{"true" if complete else "false"},raw:`'+'\n'.join(lines)+'`};\n')
    return js,len(lines)

def main():
    key=os.environ.get('MOLIT_KEY','').strip();nid=os.environ.get('NAVER_ID','').strip();sec=os.environ.get('NAVER_SECRET','').strip()
    if not key:sys.exit('MOLIT_KEY 가 없습니다 (GitHub Secrets 확인)')
    if '%' not in key:key=urllib.parse.quote(key,safe='')
    data,codes,ms,stop1=collect(key)
    want=len(codes)*len(ms)*2;got=len(data)
    agg=aggregate(data)
    print(f'받은 자료: {got}/{want} (시군구×월×매매·전세), 거래 {sum(len(r) for r in data.values()):,}건, 동 {len(agg):,}곳')
    empty=[f'{c} {codes[c][1]}' for c in codes if not any(len(data.get((k,c,m),[])) for k in('sale','rent') for m in ms)]
    if empty:print('거래가 한 건도 없는 시군구(코드 변경 가능성):',', '.join(empty))
    if not agg:sys.exit('자료를 받지 못했습니다: '+str(stop1))
    stop2=None;used=0
    if nid and sec:geo,used,stop2=locate(agg,codes,nid,sec)
    else:
        geo=json.load(open(GEO)) if os.path.exists(GEO) else {};print('NAVER_ID/NAVER_SECRET 이 없어 동 위치 찾기를 건너뜁니다')
    todo=sum(1 for (c,d),v in agg.items() if v['cx'] and f'{c}|{d}' not in geo)
    js,n=build(agg,codes,geo,ms,got>=want and not todo)
    open(os.path.join(ROOT,'prices.js'),'w',encoding='utf-8').write(js)
    print(f'동 위치: 이번에 {used}곳 찾음, 남은 {todo}곳 / prices.js 에 {n}개 동 기록')
    if stop1:print('※ 실거래가 호출이 중간에 멈췄습니다(일일 한도 등). 내일 다시 실행하면 이어서 받습니다:',stop1)
    if stop2 or todo:print('※ 동 위치가 아직 남았습니다. 다시 실행하면 이어서 찾습니다.')

if __name__=='__main__':main()
