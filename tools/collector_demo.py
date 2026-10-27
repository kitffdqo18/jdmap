"""화면 확인용 예시 데이터 생성기. 실제 사고가 아니며 제목에 '(예시)'가 붙는다."""
import random
from datetime import date, datetime, timedelta

REGIONS = {"경기": ["화성시", "평택시", "안산시", "김포시", "용인시"], "경남": ["창원시", "거제시", "김해시"],
           "경북": ["포항시", "구미시", "경주시"], "충남": ["당진시", "천안시", "아산시"], "서울": ["강남구", "영등포구"],
           "인천": ["서구", "남동구"], "전남": ["여수시", "광양시"], "충북": ["청주시", "음성군"], "울산": ["울주군", "남구"],
           "부산": ["강서구", "사하구"], "전북": ["군산시", "익산시"], "강원": ["원주시", "삼척시"], "대구": ["달서구"],
           "광주": ["광산구"], "대전": ["유성구"], "제주": ["제주시"], "세종": ["세종시"]}
CASES = [("건설업", "떨어짐", "외벽 도장 작업 중 달비계 로프가 끊어지며 약 12m 아래로 떨어짐"),
         ("건설업", "깔림·뒤집힘", "굴착기 이동 중 경사지에서 장비가 뒤집혀 운전자가 깔림"),
         ("건설업", "물체에 맞음", "타워크레인 인양 중 줄걸이가 풀려 떨어진 자재에 맞음"),
         ("제조업", "끼임", "프레스 금형 교체 중 슬라이드가 하강하여 끼임"),
         ("제조업", "화재·폭발", "탱크 내부 잔류가스가 폭발"),
         ("운수·창고업", "부딪힘", "후진하던 지게차에 부딪힘"),
         ("사업서비스업", "질식", "오폐수 저장조 청소 중 황화수소에 질식"),
         ("제조업", "감전", "분전반 점검 중 충전부에 접촉하여 감전")]


def demo_items(days=30, seed=7):
    rnd = random.Random(seed)
    today = date.today()
    out = []
    for d in range(days):
        for k in range(rnd.randint(1, 4)):
            sido = rnd.choice(list(REGIONS))
            ind, typ, text = rnd.choice(CASES)
            posted = today - timedelta(days=d)
            occ = datetime(posted.year, posted.month, posted.day, rnd.randint(7, 18), rnd.choice([0, 10, 20, 30, 40, 50])) - timedelta(days=rnd.randint(0, 1))
            dead = 1 if rnd.random() < 0.6 else 0
            out.append({"source_id": f"demo-{posted.isoformat()}-{k}", "posted_date": posted.isoformat(),
                        "occurred_at": occ.strftime("%Y-%m-%d %H:%M"), "sido": sido, "sigungu": rnd.choice(REGIONS[sido]),
                        "industry": ind, "accident_type": typ, "deaths": dead, "injuries": 0 if dead else rnd.randint(1, 2),
                        "title": f"(예시) {sido} {ind} {typ} 사고", "body": f"(예시) {text}"})
    return out
