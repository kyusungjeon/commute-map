#!/usr/bin/env python3
"""수도권 아파트 실거래가(매매·전세)를 받아 법정동별 중위가격 prices.js 와 단지별 중위가격 apts.js 를 만든다.

- 자료: 공공데이터포털 '국토교통부_아파트 매매 실거래가 자료', '국토교통부_아파트 전월세 실거래가 자료'
- 동 위치: 그 동에서 거래가 가장 많은 단지의 지번을 네이버 Geocoding 으로 한 번만 찾아 data/geo_cache.json 에 저장
- 필요한 환경변수: MOLIT_KEY, NAVER_ID, NAVER_SECRET  (GitHub Secrets 에만 넣는다. 저장소에 쓰지 않는다)
- 단지 위치: 단지 지번을 네이버 Geocoding 으로 한 번만 찾아 data/apt_geo.json 에 저장(못 찾으면 동 위치로 대신하고 표시)
- 개별 거래는 저장소에 남기지 않고 동·단지 단위 통계(중위가격·건수)만 내보낸다.
"""
import os,sys,json,time,datetime,statistics,threading,urllib.request,urllib.parse,urllib.error
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# molit2: 준공연도 포함(2026-11)
CACHE=os.path.join(ROOT,'.cache','molit2'); GEO=os.path.join(ROOT,'data','geo_cache.json')
MONTHS=int(os.environ.get('MONTHS','12')); GEO_MAX=int(os.environ.get('GEO_MAX','25000') or 25000)
APT_GEO=os.path.join(ROOT,'data','apt_geo.json')
BANDS=[40,60,85]            # 전용면적 경계: ≤40, 40~60, 60~85, 85 초과
MIN_N=3                     # 거래가 이보다 적으면 값을 비운다

SGG={ # 법정동코드 앞 5자리: (시도, 시군구)
'11110':('서울특별시','종로구'),'11140':('서울특별시','중구'),'11170':('서울특별시','용산구'),'11200':('서울특별시','성동구'),'11215':('서울특별시','광진구'),'11230':('서울특별시','동대문구'),'11260':('서울특별시','중랑구'),'11290':('서울특별시','성북구'),'11305':('서울특별시','강북구'),'11320':('서울특별시','도봉구'),'11350':('서울특별시','노원구'),'11380':('서울특별시','은평구'),'11410':('서울특별시','서대문구'),'11440':('서울특별시','마포구'),'11470':('서울특별시','양천구'),'11500':('서울특별시','강서구'),'11530':('서울특별시','구로구'),'11545':('서울특별시','금천구'),'11560':('서울특별시','영등포구'),'11590':('서울특별시','동작구'),'11620':('서울특별시','관악구'),'11650':('서울특별시','서초구'),'11680':('서울특별시','강남구'),'11710':('서울특별시','송파구'),'11740':('서울특별시','강동구'),
'28110':('인천광역시','중구'),'28140':('인천광역시','동구'),'28177':('인천광역시','미추홀구'),'28185':('인천광역시','연수구'),'28200':('인천광역시','남동구'),'28237':('인천광역시','부평구'),'28245':('인천광역시','계양구'),'28260':('인천광역시','서구'),'28710':('인천광역시','강화군'),
'41111':('경기도','수원시 장안구'),'41113':('경기도','수원시 권선구'),'41115':('경기도','수원시 팔달구'),'41117':('경기도','수원시 영통구'),'41131':('경기도','성남시 수정구'),'41133':('경기도','성남시 중원구'),'41135':('경기도','성남시 분당구'),'41150':('경기도','의정부시'),'41171':('경기도','안양시 만안구'),'41173':('경기도','안양시 동안구'),'41190':('경기도','부천시'),'41210':('경기도','광명시'),'41220':('경기도','평택시'),'41250':('경기도','동두천시'),'41271':('경기도','안산시 상록구'),'41273':('경기도','안산시 단원구'),'41281':('경기도','고양시 덕양구'),'41285':('경기도','고양시 일산동구'),'41287':('경기도','고양시 일산서구'),'41290':('경기도','과천시'),'41310':('경기도','구리시'),'41360':('경기도','남양주시'),'41370':('경기도','오산시'),'41390':('경기도','시흥시'),'41410':('경기도','군포시'),'41430':('경기도','의왕시'),'41450':('경기도','하남시'),'41461':('경기도','용인시 처인구'),'41463':('경기도','용인시 기흥구'),'41465':('경기도','용인시 수지구'),'41480':('경기도','파주시'),'41500':('경기도','이천시'),'41550':('경기도','안성시'),'41570':('경기도','김포시'),'41590':('경기도','화성시'),'41610':('경기도','광주시'),'41630':('경기도','양주시'),'41650':('경기도','포천시'),'41670':('경기도','여주시'),'41800':('경기도','연천군'),'41820':('경기도','가평군'),'41830':('경기도','양평군'),
}
for _old in('28110','28140','28260','41190','41590'):SGG.pop(_old,None)   # 개편으로 없어진 코드(2026-11 실행에서 거래 0건 확인)
# 행정구역 개편으로 코드가 바뀌었을 수 있는 곳. 최근 달에 거래가 있으면 쓰고 없으면 건너뛴다.
PROBE={'41192':('경기도','부천시 원미구'),'41194':('경기도','부천시 소사구'),'41196':('경기도','부천시 오정구'),
       '41591':('경기도','화성시 만세구'),'41593':('경기도','화성시 효행구'),'41595':('경기도','화성시 병점구'),'41597':('경기도','화성시 동탄구')}
# 인천은 2026년 7월 개편(제물포구·영종구·검단구 신설)으로 코드가 바뀌었는데 새 코드를 확인하지 못해 후보를 훑는다.
for _c in list(range(28100,28300,5))+[28112,28114,28116,28118,28142,28144,28262,28264,28266,28268]:
    if str(_c) not in SGG:PROBE[str(_c)]=('인천광역시','')
PROBE.update({'28125':('인천광역시','제물포구'),'28155':('인천광역시','영종구'),'28275':('인천광역시','서해구'),'28290':('인천광역시','검단구')})  # 2026-11 실행에서 확인된 코드
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
    """응답 XML → (rows, totalCount). row = [동, 전용면적, 금액(만원), 단지명, 지번, 준공연도]"""
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
        rows.append([dong,area,amt,g('aptNm'),g('jibun'),g('buildYear')])
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
        for k in range(6):
            xml=http(f"{API[kind]}?serviceKey={key}&LAWD_CD={code}&DEAL_YMD={ym}&pageNo={page}&numOfRows=1000")
            try:r,total=parse(kind,xml);break
            except ApiStop as e:
                if 'PER_SECOND' not in str(e) or k==5:raise
                time.sleep(2+k)                      # 초당 한도에 걸리면 잠깐 쉬고 다시
        rows+=r
        if page*1000>=total:break
        page+=1
    return rows

def collect(key,today=None):
    os.makedirs(CACHE,exist_ok=True)
    ms=months(MONTHS,today);fresh=set(ms[:2]);data={};codes=dict(SGG);stop=[]
    def probe(c):
        if stop:return c,False
        try:return c,bool(fetch('sale',c,ms[1],key))
        except ApiStop as e:stop.append(str(e));return c,False
    with ThreadPoolExecutor(4) as ex:
        for c,ok in ex.map(probe,list(PROBE)):
            if ok:codes[c]=PROBE[c];print('개편 코드 사용:',c,PROBE[c],flush=True)
    todo=[]
    for kind in('sale','rent'):
        for ym in ms:                                   # 최근 달부터
            for code in codes:
                f=os.path.join(CACHE,f'{kind}_{code}_{ym}.json')
                if os.path.exists(f) and ym not in fresh:data[(kind,code,ym)]=json.load(open(f))
                else:todo.append((kind,code,ym,f))
    done=[0];lock=threading.Lock()
    def work(t):
        kind,code,ym,f=t
        if not stop:
            try:
                rows=fetch(kind,code,ym,key);json.dump(rows,open(f,'w'),ensure_ascii=False)
                with lock:
                    done[0]+=1
                    if done[0]%100==0:print(f'  실거래가 {done[0]}/{len(todo)} 받는 중',flush=True)
                return (kind,code,ym),rows
            except ApiStop as e:
                if not stop:print('!! 호출 중단:',e,flush=True)
                stop.append(str(e))
        return ((kind,code,ym),json.load(open(f))) if os.path.exists(f) else None
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(work,todo):
            if r:data[r[0]]=r[1]
    return data,codes,ms,(stop[0] if stop else None)

def band(a):return sum(a>b for b in BANDS)

def aggregate(data):
    """→ {(code,동): {'s':[4 lists],'j':[4 lists],'cx':{(단지,지번):건수}}}"""
    out={}
    for (kind,code,ym),rows in data.items():
        for dong,area,amt,apt,jibun,*_ in rows:
            d=out.setdefault((code,dong),{'s':[[],[],[],[]],'j':[[],[],[],[]],'cx':{}})
            d['s' if kind=='sale' else 'j'][band(area)].append(amt)
            if jibun:d['cx'][(apt,jibun)]=d['cx'].get((apt,jibun),0)+1
    return out

def aggregate_apts(data):
    """→ {(code,동,단지,지번): {'s':[4],'j':[4],'y':{준공연도:건수}}}"""
    out={}
    for (kind,code,ym),rows in data.items():
        for row in rows:
            dong,area,amt,apt,jibun=row[:5];yr=row[5] if len(row)>5 else ''
            if not apt or not jibun:continue
            d=out.setdefault((code,dong,apt.strip(),jibun.strip()),{'s':[[],[],[],[]],'j':[[],[],[],[]],'y':{}})
            d['s' if kind=='sale' else 'j'][band(area)].append(amt)
            if yr:d['y'][yr]=d['y'].get(yr,0)+1
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
        if used and used%200==0:print(f'  동 위치 {used}곳 찾는 중',flush=True)
        try:
            pt=geocode(' '.join(x for x in(sido,sgg,dong,jibun) if x),nid,sec);used+=1
            geo[k]=pt or geocode(' '.join(x for x in(sido,sgg,dong) if x),nid,sec) or []
            if not pt:used+=1
            time.sleep(0.05)
        except ApiStop as e:stopped=str(e);print('!! 주소 찾기 중단:',stopped)
    os.makedirs(os.path.dirname(GEO),exist_ok=True)
    json.dump(geo,open(GEO,'w'),ensure_ascii=False,sort_keys=True,indent=0)
    return geo,used,stopped

def locate_apts(apts,codes,nid,sec,budget):
    """단지 지번 위치 찾기. 거래 많은 단지부터, 여러 개를 동시에. 일일 한도에 걸리면 멈추고 다음 실행에 이어 간다."""
    geo=json.load(open(APT_GEO)) if os.path.exists(APT_GEO) else {}
    todo=[k for k,v in sorted(apts.items(),key=lambda kv:-sum(len(x) for x in kv[1]['s']+kv[1]['j'])) if f'{k[0]}|{k[1]}|{k[3]}' not in geo][:max(budget,0)]
    stop=[];done=[0];lock=threading.Lock()
    def work(k):
        if stop:return None
        code,dong,apt,jibun=k;sido,sgg=codes[k[0]]
        try:pt=geocode(' '.join(x for x in(sido,sgg,dong,jibun) if x),nid,sec)
        except ApiStop as e:
            if not stop:print('!! 단지 위치 찾기 중단:',e,flush=True)
            stop.append(str(e));return None
        with lock:
            done[0]+=1
            if done[0]%1000==0:print(f'  단지 위치 {done[0]}/{len(todo)} 찾는 중',flush=True)
        return f'{code}|{dong}|{jibun}',(pt or [])
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(work,todo):
            if r:geo[r[0]]=r[1]
    os.makedirs(os.path.dirname(APT_GEO),exist_ok=True)
    json.dump(geo,open(APT_GEO,'w'),ensure_ascii=False,sort_keys=True,indent=0)
    left=sum(1 for k in apts if f'{k[0]}|{k[1]}|{k[3]}' not in geo)
    return geo,done[0],(stop[0] if stop else None),left

def build_apts(apts,codes,ageo,dgeo,ms,complete):
    """apts.js: 단지명|위도,경도|시군구 동|준공연도|매매 4칸|전세 4칸|위치표시. 각 칸 '중위가격:건수'(만원), 거래 없으면 빈칸.
    위치표시 a = 지번을 못 찾아 동 위치로 대신함."""
    def cell(v):return f"{int(round(statistics.median(v)))}:{len(v)}" if v else ''
    lines=[]
    for k,d in sorted(apts.items()):
        code,dong,apt,jibun=k;pt=ageo.get(f'{code}|{dong}|{jibun}');flag=''
        if not pt:pt=dgeo.get(f'{code}|{dong}');flag='a'
        if not pt:continue
        sido,sgg=codes[code];label=('인천 '+sgg).strip() if sido.startswith('인천') else sgg
        yr=max(d['y'].items(),key=lambda kv:kv[1])[0] if d['y'] else ''
        nm=apt.replace('|',' ').replace('`',"'")
        lines.append(f"{nm}|{pt[0]},{pt[1]}|{label} {dong}|{yr}|{','.join(cell(x) for x in d['s'])}|{','.join(cell(x) for x in d['j'])}|{flag}")
    period=f"{ms[-1][:4]}년 {int(ms[-1][4:])}월~{ms[0][:4]}년 {int(ms[0][4:])}월"
    js=("// 수도권 아파트 단지별 실거래 중위가격(만원)과 건수. tools/fetch_prices.py 가 만든다. 출처: 국토교통부 실거래가 공개자료\n"
        "// 형식: 단지명|위도,경도|시군구 동|준공연도|매매(≤40,40~60,60~85,85초과 각 '중위:건수')|전세(같은 순서)|a=위치가 동 중심(대략)\n"
        f'window.APTS={{period:"{period}",made:"{datetime.date.today().isoformat()}",complete:{"true" if complete else "false"},raw:`'+'\n'.join(lines)+'`};\n')
    return js,len(lines)

def med(v):return str(int(round(statistics.median(v)))) if len(v)>=MIN_N else ''

def build(agg,codes,geo,ms,complete):
    lines=[]
    for (code,dong),d in sorted(agg.items()):
        pt=geo.get(f'{code}|{dong}')
        if not pt:continue
        s=[med(x) for x in d['s']];j=[med(x) for x in d['j']]
        if not any(s+j):continue
        sido,sgg=codes[code];label=('인천 '+sgg).strip() if sido.startswith('인천') else sgg
        lines.append(f"{label} {dong}|{pt[0]},{pt[1]}|{','.join(s)}|{','.join(j)}")
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
    open(os.path.join(ROOT,'commute','prices.js'),'w',encoding='utf-8').write(js)
    print(f'동 위치: 이번에 {used}곳 찾음, 남은 {todo}곳 / prices.js 에 {n}개 동 기록')
    apts=aggregate_apts(data);stop3=None;aused=0
    if nid and sec:ageo,aused,stop3,aleft=locate_apts(apts,codes,nid,sec,GEO_MAX-used)
    else:
        ageo=json.load(open(APT_GEO)) if os.path.exists(APT_GEO) else {};aleft=sum(1 for k in apts if f'{k[0]}|{k[1]}|{k[3]}' not in ageo)
    ajs,an=build_apts(apts,codes,ageo,geo,ms,got>=want and not aleft)
    open(os.path.join(ROOT,'commute','apts.js'),'w',encoding='utf-8').write(ajs)
    miss=sum(1 for v in ageo.values() if not v)
    print(f'단지: {len(apts):,}곳 / 위치 이번에 {aused:,}곳 찾음, 남은 {aleft:,}곳, 지번으로 못 찾아 동 위치로 대신 {miss:,}곳 / apts.js 에 {an:,}개 단지 기록({len(ajs)//1024:,}KB)')
    if stop3 or aleft:print('※ 단지 위치가 아직 남았습니다. 네이버 Geocoding 일일 한도를 확인하고 다시 실행하면 이어서 찾습니다.')
    if stop1:print('※ 실거래가 호출이 중간에 멈췄습니다(일일 한도 등). 내일 다시 실행하면 이어서 받습니다:',stop1)
    if stop2 or todo:print('※ 동 위치가 아직 남았습니다. 다시 실행하면 이어서 찾습니다.')

if __name__=='__main__':main()
