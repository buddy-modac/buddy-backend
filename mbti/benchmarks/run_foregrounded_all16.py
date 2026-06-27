"""Phase C — foregrounded generic behavioral (distinguishing axis emphasised), all 16, K=5."""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from personaforge import BASE_ASSISTANT, PRIORITIES, ModelClient, Cache, ClaudeCLIBackend, ALL_TYPES
from personaforge.style import foregrounded_behavioral_style
from personaforge.identify import _MBTI_JUDGE_SYSTEM
from personaforge.model import Message, extract_json
HERE=os.path.dirname(__file__); REPORT=os.path.join(HERE,"foregrounded_all16_20260626.md")
CACHE=os.path.abspath(os.path.join(HERE,"..","personas","local","blind_cache.db")); K=5
PROBES=["내일 비 온대, 우산 챙길까?","와이파이가 자꾸 끊겨, 어떻게 고쳐?","주말에 갈 만한 당일치기 여행지 추천해줘","점심 뭐 먹을지 못 정하겠어"]
FAM={**{t:"NT" for t in["INTJ","INTP","ENTJ","ENTP"]},**{t:"NF" for t in["INFJ","INFP","ENFJ","ENFP"]},**{t:"SJ" for t in["ISTJ","ISFJ","ESTJ","ESFJ"]},**{t:"SP" for t in["ISTP","ISFP","ESTP","ESFP"]}}
def sysp(t): return f"[ASSISTANT]\n{BASE_ASSISTANT} Always answer in Korean.\n\n[COMMUNICATION STYLE]\n{foregrounded_behavioral_style(t)}\n\n[PRIORITIES & GUARDRAILS]\n{PRIORITIES}"
def w(l):
    with open(REPORT,"a",encoding="utf-8") as f: f.write(l+"\n")
def judge(c,l,k):
    try: return str(extract_json(c.complete(_MBTI_JUDGE_SYSTEM,[Message("user",l)],150+k)).get("type","")).strip().upper()[:4]
    except: return "?"
def main():
    c=ModelClient(model="claude-sonnet-4-6",cache=Cache(CACHE),backend=ClaudeCLIBackend()); open(REPORT,"w").close()
    w(f"# Phase C — foregrounded generic, 16유형 (K={K})\n"); w("| 유형 | 정확 | 패밀리 | P등록 | 분포 |\n|---|---|---|---|---|")
    ax={"EI":0,"SN":0,"TF":0,"JP":0}; ex_t=fm_t=pr_t=0; N=len(ALL_TYPES)*K
    for t in ALL_TYPES:
        ans=[c.complete(sysp(t),[Message("user",q)],250) for q in PROBES]
        listing="\n\n".join(f"Q:{q}\nA:{a}" for q,a in zip(PROBES,ans)); g=[judge(c,listing,k) for k in range(K)]
        ex=sum(1 for x in g if x==t); fm=sum(1 for x in g if FAM.get(x)==FAM[t]); pr=sum(1 for x in g if len(x)==4 and x[3]=="P")
        ex_t+=ex; fm_t+=fm; pr_t+=pr
        for x in g:
            if len(x)==4:
                for i,axn in enumerate(["EI","SN","TF","JP"]):
                    if x[i]==t[i]: ax[axn]+=1
        w(f"| {t} | {ex}/{K} | {fm}/{K} | {pr}/{K} | {', '.join(f'{x}×{n}' for x,n in Counter(g).most_common())} |")
        print(f"{t}: 정확{ex} P{pr}",flush=True)
    w(f"\n## 축별 (/{N})\n| 지표 | foregrounded | 큐레이션B | 묘사형 |\n|---|---|---|---|")
    w(f"| 정확 | {100*ex_t//N}% | 30% | 12% |"); w(f"| 패밀리 | {100*fm_t//N}% | 43% | 25% |")
    for a in ["EI","SN","TF","JP"]: w(f"| {a} | {100*ax[a]//N}% | - | - |")
    w(f"| P등록 | {pr_t}/{N} | 10/80 | ~0 |"); w("\n<!-- DONE -->")
    print(f"DONE 정확{100*ex_t//N}% P{pr_t}/{N}",flush=True)
main()
