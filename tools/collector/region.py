"""사고 게시글 본문에서 시도·시군구·업종·재해유형·인원·일시를 뽑아내는 규칙.

사이렌 게시글 형식이 확정되면 tests/test_extract.py 에 실제 문장 예시를 추가하고
여기 규칙을 보완한다. 규칙으로 못 뽑은 값은 비워 두고 관리자 화면에서 수정한다.
"""
import re
from datetime import datetime

SIDO_ALIASES = {
    "서울": ["서울특별시", "서울시", "서울"],
    "부산": ["부산광역시", "부산시", "부산"],
    "대구": ["대구광역시", "대구시", "대구"],
    "인천": ["인천광역시", "인천시", "인천"],
    "광주": ["광주광역시"],  # '광주시'는 경기도 광주시와 겹치므로 별도 처리
    "대전": ["대전광역시", "대전시", "대전"],
    "울산": ["울산광역시", "울산시", "울산"],
    "세종": ["세종특별자치시", "세종시", "세종"],
    "경기": ["경기도", "경기"],
    "강원": ["강원특별자치도", "강원도", "강원"],
    "충북": ["충청북도", "충북"],
    "충남": ["충청남도", "충남"],
    "전북": ["전북특별자치도", "전라북도", "전북"],
    "전남": ["전라남도", "전남"],
    "경북": ["경상북도", "경북"],
    "경남": ["경상남도", "경남"],
    "제주": ["제주특별자치도", "제주도"],
}
SIDO_FULL = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시",
    "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도", "강원": "강원특별자치도",
    "충북": "충청북도", "충남": "충청남도", "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}
SIDO_LIST = list(SIDO_FULL)

# 도 단위 시·군 → 시도 (광역시 '구'는 이름이 겹쳐서 시도가 함께 적힌 경우에만 인정)
_SIGUN = {
    "경기": "수원시 성남시 의정부시 안양시 부천시 광명시 평택시 동두천시 안산시 고양시 과천시 구리시 남양주시 오산시 시흥시 군포시 의왕시 하남시 용인시 파주시 이천시 안성시 김포시 화성시 양주시 포천시 여주시 연천군 가평군 양평군",
    "강원": "춘천시 원주시 강릉시 동해시 태백시 속초시 삼척시 홍천군 횡성군 영월군 평창군 정선군 철원군 화천군 양구군 인제군 양양군",
    "충북": "청주시 충주시 제천시 보은군 옥천군 영동군 증평군 진천군 괴산군 음성군 단양군",
    "충남": "천안시 공주시 보령시 아산시 서산시 논산시 계룡시 당진시 금산군 부여군 서천군 청양군 홍성군 예산군 태안군",
    "전북": "전주시 군산시 익산시 정읍시 남원시 김제시 완주군 진안군 무주군 장수군 임실군 순창군 고창군 부안군",
    "전남": "목포시 여수시 순천시 나주시 광양시 담양군 곡성군 구례군 고흥군 보성군 화순군 장흥군 강진군 해남군 영암군 무안군 함평군 영광군 장성군 완도군 진도군 신안군",
    "경북": "포항시 경주시 김천시 안동시 구미시 영주시 영천시 상주시 문경시 경산시 의성군 청송군 영양군 영덕군 청도군 고령군 성주군 칠곡군 예천군 봉화군 울진군 울릉군",
    "경남": "창원시 진주시 통영시 사천시 김해시 밀양시 거제시 양산시 의령군 함안군 창녕군 남해군 하동군 산청군 함양군 거창군 합천군",
    "제주": "제주시 서귀포시",
    "부산": "기장군",
    "대구": "달성군 군위군",
    "인천": "강화군 옹진군",
    "울산": "울주군",
}
SIGUN_TO_SIDO = {name: sido for sido, names in _SIGUN.items() for name in names.split()}
AMBIGUOUS_SIGUN = {"고성군": ("강원", "경남"), "광주시": ("경기",)}  # 고성군은 시도 없이는 판단 불가

ACCIDENT_TYPES = [
    ("떨어짐", ["떨어짐", "떨어져", "추락", "떨어지"]),
    ("끼임", ["끼임", "끼여", "끼어", "협착"]),
    ("깔림·뒤집힘", ["깔림", "깔려", "뒤집힘", "전도", "넘어지며", "전복"]),
    ("부딪힘", ["부딪힘", "부딪혀", "충돌", "치임", "치여"]),
    ("물체에 맞음", ["맞음", "맞아", "낙하물", "비래"]),
    ("화재·폭발", ["폭발", "화재", "불이"]),
    ("질식", ["질식", "중독", "산소결핍"]),
    ("감전", ["감전"]),
    ("무너짐", ["무너짐", "무너져", "붕괴"]),
]
INDUSTRY_RULES = [
    ("건설업", ["건설", "공사", "현장", "신축", "철거", "토목", "아파트", "도로", "교량"]),
    ("제조업", ["제조", "공장", "생산", "프레스", "사출", "금형", "가공"]),
    ("운수·창고업", ["물류", "창고", "운송", "택배", "하역", "항만"]),
    ("농림어업", ["농장", "벌목", "어선", "양식", "축사"]),
    ("광업", ["광산", "채석", "갱"]),
]

_SIDO_PAT = re.compile("|".join(sorted({a for v in SIDO_ALIASES.values() for a in v}, key=len, reverse=True)))
_SGG_AFTER = re.compile(r"\s*([가-힣]{1,5}(?:시|군|구))(?:\s*([가-힣]{1,5}구))?")
_SIGUN_PAT = re.compile(r"([가-힣]{1,4}(?:시|군))(?![가-힣])")


def extract_region(text):
    """(시도, 시군구) 반환. 못 찾으면 None."""
    text = text or ""
    m = _SIDO_PAT.search(text)
    if m:
        alias = m.group(0)
        sido = next(k for k, v in SIDO_ALIASES.items() if alias in v)
        after = _SGG_AFTER.match(text, m.end())
        sgg = None
        if after:
            cand = after.group(1)
            if cand not in {"특별시", "광역시", "자치시"} and not cand.endswith("특별자치시"):
                sgg = cand + (" " + after.group(2) if after.group(2) else "")
        if sido == "세종":
            sgg = sgg if sgg and sgg != "세종시" else "세종시"
        return sido, sgg
    if "광주시" in text and "광주광역시" not in text:
        return "경기", "광주시"
    for m2 in _SIGUN_PAT.finditer(text):
        name = m2.group(1)
        if name in AMBIGUOUS_SIGUN:
            continue
        if name in SIGUN_TO_SIDO:
            return SIGUN_TO_SIDO[name], name
    return None, None


def extract_type(text):
    text = text or ""
    best, pos = None, None
    for label, kws in ACCIDENT_TYPES:
        for kw in kws:
            i = text.find(kw)
            if i >= 0 and (pos is None or i < pos):
                best, pos = label, i
    return best


def extract_industry(text):
    text = text or ""
    for label in ("건설업", "제조업", "운수·창고업", "농림어업", "광업", "서비스업", "도소매업"):
        if label in text:
            return label
    for label, kws in INDUSTRY_RULES:
        if any(k in text for k in kws):
            return label
    return None


def _count(text, word):
    m = re.search(rf"(\d+)\s*명\s*(?:이\s*)?{word}", text) or re.search(rf"{word}\s*(\d+)\s*명", text)
    if m:
        return int(m.group(1))
    return None


def extract_people(text):
    """(사망자, 부상자)."""
    text = text or ""
    dead = _count(text, "사망")
    if dead is None:
        dead = 1 if re.search(r"사망|숨[졌지]", text) else 0
    inj = _count(text, "(?:부상|중상|경상)")
    if inj is None:
        inj = 1 if re.search(r"부상|중상|경상|다침|다쳐", text) and not dead else 0
    return dead, inj


_DATE = re.compile(r"(?<!\d)(\d{4}|\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?")
_TIME = re.compile(r"(오전|오후)?\s*(\d{1,2})\s*(?::|시)\s*(\d{1,2})?\s*분?")


def extract_datetime(text):
    """'YYYY-MM-DD HH:MM' 또는 'YYYY-MM-DD' 또는 None."""
    text = text or ""
    m = _DATE.search(text)
    if not m:
        return None
    y, mo, d = m.groups()
    y = int(y) + (2000 if len(y) == 2 else 0)
    try:
        dt = datetime(y, int(mo), int(d))
    except ValueError:
        return None
    t = _TIME.search(text, m.end(), m.end() + 30)
    if t and (t.group(1) or ":" in t.group(0) or "시" in t.group(0)):
        h = int(t.group(2))
        mi = int(t.group(3) or 0)
        if t.group(1) == "오후" and h < 12:
            h += 12
        if t.group(1) == "오전" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            return dt.replace(hour=h, minute=mi).strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d")
