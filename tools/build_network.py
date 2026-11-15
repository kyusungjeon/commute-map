# stations.js(역명|좌표|노선)에서 노선별 역 연결(network.js)을 만든다.
# 역 순서 원자료가 없어 "같은 노선의 가까운 역끼리 잇는" 최소신장트리로 추정하고,
# 실제와 다른 부분은 아래 ADD/FORCE/FORBID 로 바로잡는다.
import math,collections,sys
src=open('stations.js',encoding='utf-8').read()
head,body=src.split('`')[0],src.split('`')[1]
S=[]
for l in body.split('\n'):
    n,c,ln=l.split('|');la,lo=map(float,c.split(','));S.append([n,la,lo,ln.split(',')])
def base(n):return n.split('(')[0]
def idx(name,line=None):
    c=[i for i,s in enumerate(S) if (s[0]==name or base(s[0])==name) and (line is None or line in s[3])]
    if len(c)!=1:
        c2=[i for i in c if S[i][0]==name]
        if len(c2)==1:return c2[0]
        raise SystemExit(f'역 찾기 실패: {name} {line} {[S[i][0] for i in c]}')
    return c[0]
# 원자료에 빠진 운행 노선 보정
ADD={'경의중앙선':['이촌','서빙고','한남','옥수','응봉','왕십리','용산','청량리','회기'],
     '수인분당선':['왕십리','청량리','한대앞','중앙','고잔','초지','안산','신길온천','정왕','오이도'],
     '1호선':['회기'],'2호선':['까치산'],'경춘선':['망우','상봉']}
DROP={'1호선':['이촌','서빙고','한남','옥수','응봉','왕십리']}
for ln,names in DROP.items():
    for n in names:
        for st in S:
            if base(st[0])==n and ln in st[3]:st[3].remove(ln)
for ln,names in ADD.items():
    for n in names:
        c=[i for i,s in enumerate(S) if base(s[0])==n and not s[0].endswith('(GTX-A)')]
        assert len(c)==1,(n,c)
        if ln not in S[c[0]][3]:S[c[0]][3].append(ln)
FORCE={'2호선':[('당산','합정'),('성수','용답'),('용답','신답'),('신답','용두'),('용두','신설동'),('신도림','도림천'),('도림천','양천구청'),('양천구청','신정네거리'),('신정네거리','까치산'),('대림','신도림'),('강변','잠실나루'),('구로디지털단지','대림'),('신당','상왕십리'),('상왕십리','왕십리'),('왕십리','한양대'),('한양대','뚝섬'),('뚝섬','성수'),('성수','건대입구')],
       '6호선':[('응암','역촌'),('역촌','불광'),('불광','독바위'),('독바위','연신내'),('연신내','구산'),('구산','응암')],
       '1호선':[('금천구청','광명'),('금천구청','석수'),('석수','관악'),('병점','세마'),('구로','구일'),('구로','가산디지털단지'),('병점','서동탄'),('남영','용산'),('용산','노량진'),('청량리','회기'),('제기동','청량리')],
       '경의중앙선':[('가좌','신촌'),('신촌','서울역'),('가좌','홍대입구'),('홍대입구','서강대'),('서강대','공덕'),('공덕','효창공원앞'),('효창공원앞','용산'),('용산','이촌'),('이촌','서빙고'),('서빙고','한남'),('한남','옥수'),('옥수','응봉'),('응봉','왕십리'),('왕십리','청량리'),('청량리','회기'),('회기','중랑')],
       '의정부경전철':[('경전철의정부','의정부시청'),('의정부시청','흥선'),('흥선','의정부중앙'),('의정부중앙','동오')],
       '수인분당선':[('왕십리','서울숲'),('청량리','왕십리'),('사리','한대앞'),('오이도','달월')],
       '경춘선':[('상봉','망우'),('망우','신내')]}
RING2='시청 을지로입구 을지로3가 을지로4가 동대문역사문화공원 신당 상왕십리 왕십리 한양대 뚝섬 성수 건대입구 구의 강변 잠실나루 잠실 잠실새내 종합운동장 삼성 선릉 역삼 강남 교대 서초 방배 사당 낙성대 서울대입구 봉천 신림 신대방 구로디지털단지 대림 신도림 문래 영등포구청 당산 합정 홍대입구 신촌 이대 아현 충정로'.split()
FORCE['2호선']+=[(RING2[k],RING2[(k+1)%len(RING2)]) for k in range(len(RING2))]
def d(a,b):return math.hypot((S[a][1]-S[b][1])*111,(S[a][2]-S[b][2])*88)
L=collections.defaultdict(list)
for i,s in enumerate(S):
    for ln in s[3]:L[ln].append(i)
EDGES=[];rep=[]
for ln,ids in sorted(L.items()):
    par={i:i for i in ids}
    def f(x):
        while par[x]!=x:par[x]=par[par[x]];x=par[x]
        return x
    E=[]
    for a,b in FORCE.get(ln,[]):
        a,b=idx(a,ln),idx(b,ln)
        if (a,b) in E or (b,a) in E:continue
        E.append((a,b));par[f(a)]=f(b)   # 순환(2호선 등)은 그대로 둔다
    for w,a,b in sorted((d(a,b),a,b) for k,a in enumerate(ids) for b in ids[k+1:]):
        if f(a)!=f(b):par[f(a)]=f(b);E.append((a,b))
    deg=collections.Counter()
    for a,b in E:deg[a]+=1;deg[b]+=1;EDGES.append((a,b,ln))
    rep.append(f"{ln} {len(ids)}역 | 분기 {[S[i][0] for i in ids if deg[i]>2]} | 끝 {[S[i][0] for i in ids if deg[i]==1]} | 최장 {max((round(d(a,b),1),S[a][0],S[b][0]) for a,b in E)}")
print('\n'.join(rep))
lines=sorted(L)
if '--write' in sys.argv:
    open('stations.js','w',encoding='utf-8').write(head+'`'+'\n'.join(f"{s[0]}|{s[1]:.4f},{s[2]:.4f}|{','.join(s[3])}" for s in S)+'`;\n')
    open('network.js','w',encoding='utf-8').write('// 노선별 역 연결(추정). tools/build_network.py 로 생성. 형식: 역번호,역번호,노선번호 (역번호는 stations.js 줄 순서)\nwindow.NET_LINES='+repr(lines).replace("'",'"')+';\nwindow.NET_EDGES="'+';'.join(f"{a},{b},{lines.index(ln)}" for a,b,ln in EDGES)+'";\n')
    print('written',len(EDGES))
