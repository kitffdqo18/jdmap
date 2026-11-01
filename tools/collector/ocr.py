"""사이렌 포스터 그림에서 글자 읽기 (OCR).

중대재해 사이렌은 사고 내용이 글자가 아니라 포스터 그림(PNG) 안에 있다.
포스터 양식이 고정이라(가로 992 × 세로 1403 기준) 정해진 칸만 잘라서 읽는다.
  - 사고 내용 칸: "'26년 10월 28일(수) 10:10경 경기 고양시 소재 ... 사망"
  - 업종 칸 / 재해유형 칸

필요한 프로그램: tesseract-ocr + 한국어 데이터(tesseract-ocr-kor), 파이썬 Pillow
(GitHub Actions 에서는 collect.yml 이 설치한다)
"""
import base64
import difflib
import io
import re
import shutil
import subprocess
import tempfile

# 읽는 방식을 고치면 숫자를 올린다 → 이미 모은 게시물도 한 번 다시 읽는다
VERSION = 2

BASE_W, BASE_H = 992, 1403
# (x, y, 가로, 세로) — 기준 크기 좌표. 그림 크기가 다르면 비율로 맞춘다.
BOX_TEXT = (75, 430, 850, 190)   # 세로 길이는 글 줄 수에 따라 text_bottom() 으로 다시 잰다
BOX_INDUSTRY = (400, 300, 135, 45)
BOX_TYPE = (545, 300, 165, 45)

INDUSTRIES = ["건설업", "제조업", "운수·창고업", "도소매업", "숙박·음식점업", "사업서비스업", "농림어업", "광업", "기타"]
TYPES = ["떨어짐", "넘어짐", "깔림·뒤집힘", "부딪힘", "맞음", "무너짐", "끼임", "절단·베임", "감전", "폭발·파열",
         "화재", "불균형 및 무리한 동작", "이상온도 접촉", "화학물질 누출·접촉", "산소결핍", "질병", "교통사고", "기타"]
# 포스터 표기 → 사이트 분류 이름
TYPE_TO_SITE = {"맞음": "물체에 맞음", "폭발·파열": "화재·폭발", "화재": "화재·폭발", "산소결핍": "질식"}


def available():
    return shutil.which("tesseract") is not None


def decode_data_url(s):
    """'data:image/...;base64,xxxx' 또는 순수 base64 → bytes."""
    if not s:
        return None
    if "," in s[:100]:
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s)
    except Exception:
        return None


def _prep(img, box, scale, threshold=150):
    from PIL import Image

    sx, sy = img.width / BASE_W, img.height / BASE_H
    x, y, w, h = box
    c = img.crop((int(x * sx), int(y * sy), int((x + w) * sx), int((y + h) * sy))).convert("L")
    c = c.resize((max(1, int(c.width * scale / sx)), max(1, int(c.height * scale / sy))), Image.LANCZOS)
    return c.point(lambda v: 0 if v < threshold else 255)


def text_bottom(img):
    """사고 내용 칸의 아래 끝(기준 좌표). 글 아래 사진이 시작되는 줄을 찾는다.
    사진 줄은 흰색·검은색이 아닌 중간 밝기 점이 많다. 3줄 글이면 약 620, 4줄이면 약 670."""
    g = img.convert("L").resize((BASE_W, BASE_H))
    px = g.load()
    run = 0
    for y in range(440, 760):
        mid = sum(1 for x in range(100, 900, 2) if 70 < px[x, y] < 215)
        if mid / 400 > 0.35:
            run += 1
            if run >= 8:
                return max(600, min(720, y - 8))
        else:
            run = 0
    return 720


def _tess(img, psm):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        img.save(f.name)
        r = subprocess.run(["tesseract", f.name, "stdout", "-l", "kor", "--psm", str(psm)],
                           capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "ignore")


# 자주 틀리는 글자 바로잡기 (실제 사이렌 포스터 읽기 결과에서 모은 것)
FIXES = [
    (r"(\d{1,2})\s*[훨휠윌될뭘월]", r"\1월"),
    (r"소[새세]\b", "소재"), (r"소새", "소재"),
    (r"현[상창](?=(에서|메서|어서|내|\s))", "현장"),
    (r"(?<=[가-힣\s])[제세]소(?=\s|공장|사업|업)", "제조"), (r"세조", "제조"), (r"세분", "제분"),
    (r"메서", "에서"), (r"(?<=[장상])어서", "에서"),
    (r"사업상|시업장|사업창", "사업장"), (r"공상(?=\s|에서|내)", "공장"),
    (r"[재새자깨][해애]자|재[해애]사|재애자", "재해자"),
    (r"지게자", "지게차"), (r"회물", "화물"), (r"[삭식]업", "작업"), (r"포상(?=공사|용)", "포장"),
    (r"부[딪덧뒷및][혀여]", "부딪혀"), (r"[사시4]망", "사망"), (r"쿨착기", "굴착기"),
    (r"(?<![가-힣])중북", "충북"), (r"(?<![가-힣])중남", "충남"), (r"(?<![가-힣])제수(?=\s)", "제주"),
    (r"전남광[주수]", "전남광주"),
]


def _clean(s):
    s = re.sub(r"[\r\n]+", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lstrip("'‘’`\"| ").strip()
    # 날짜 앞의 '26년 → 2026년 (연도 인식을 돕기 위해)
    s = re.sub(r"^[‘’'`]?\s*(\d{2})\s*년", lambda m: f"20{m.group(1)}년", s)
    for a, b in FIXES:
        s = re.sub(a, b, s)
    # 'N일(요일)' 부분이 깨져도 날짜·시각이 읽히도록: 28일기 → 28일, 24임토) → 24일, 15앨목| → 15일
    s = re.sub(r"(\d{1,2})\s*[일앨앰임밀잂]\s*[^\d\s]{0,4}\s*(?=\d{1,2}\s*[:.시]\s*\d)", r"\1일 ", s)
    s = re.sub(r"(\d{1,2})\s*\.\s*(\d{2})\s*경", r"\1:\2경", s)  # 12.10경 → 12:10경
    return _fix_region(s)


def _jamo(text):
    out = []
    for ch in text:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [chr(0x1100 + c // 588), chr(0x1161 + (c % 588) // 28)]
            if c % 28:
                out.append(chr(0x11A7 + c % 28))
        else:
            out.append(ch)
    return "".join(out)


def _fix_region(s):
    """'…경 충북 음선군 소재' 처럼 시군 이름이 조금 틀리면 가장 비슷한 시군으로 바로잡는다."""
    from . import region

    m = re.search(r"경\s*([가-힣]{2,7})\s+([가-힣]{1,4}[시군구])(?=\s)", s)
    if not m:
        # '경기 고양 소재' 처럼 끝의 시·군이 빠진 경우
        m2 = re.search(r"경\s*([가-힣]{2,7})\s+([가-힣]{1,3})(?=\s*소재)", s)
        if m2:
            for tail in ("시", "군"):
                if m2.group(2) + tail in region.SIGUN_TO_SIDO:
                    return s[:m2.end(2)] + tail + s[m2.end(2):]
        return s
    sido_word, sgg = m.group(1), m.group(2)
    if sido_word.startswith("전남광주"):  # 2026.7 광주·전남 통합: 구는 옛 광주, 시군은 옛 전남
        new = "광주광역시" if sgg in ("동구", "서구", "남구", "북구", "광산구") else "전남"
        return s[:m.start(1)] + new + s[m.end(1):]
    if sgg in region.SIGUN_TO_SIDO:
        return s
    names = list(region.SIGUN_TO_SIDO)
    sido = next((k for k, v in region.SIDO_ALIASES.items() if sido_word in v), None)
    if sido:
        names = [n for n in names if region.SIGUN_TO_SIDO[n] == sido] or names
        if sido in ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종") and sgg.endswith("구"):
            return s  # 광역시의 구는 그대로
    # 글자를 자모로 풀어서 비교 (중수시 ↔ 충주시 처럼 받침·자음 하나 틀린 경우도 찾게)
    target = _jamo(sgg)
    scored = sorted(((difflib.SequenceMatcher(None, target, _jamo(n)).ratio(), n) for n in names), reverse=True)
    if not scored or scored[0][0] < 0.65 or (len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05):
        return s
    fixed = scored[0][1]
    new_sido = sido_word if sido else region.SIDO_FULL[region.SIGUN_TO_SIDO[fixed]]
    return s[:m.start(1)] + new_sido + " " + fixed + s[m.end(2):]


def _pick(raw, choices):
    t = re.sub(r"[^가-힣·]", "", raw or "")
    if not t:
        return None
    for c in choices:
        if c.replace("·", "") in t.replace("·", ""):
            return c
    best = difflib.get_close_matches(t, choices, n=1, cutoff=0.4)
    if best:
        return best[0]
    # 앞 두 글자만 맞아도 인정 (예: '떨어' → 떨어짐, '무너5' → 무너짐)
    for c in choices:
        if len(t) >= 2 and c.startswith(t[:2]):
            return c
    return None


def read_poster(png_bytes):
    """포스터 그림 → {'body', 'industry', 'accident_type'}. 실패하면 빈 dict."""
    if not png_bytes or not available():
        return {}
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
    except Exception:
        return {}
    ratio = (img.height / img.width) / (BASE_H / BASE_W)
    if not 0.9 < ratio < 1.1:
        # 양식이 다른 그림이면 통째로 읽는다
        return {"body": _clean(_tess(img.convert("L"), 3))}
    x, y, w, _ = BOX_TEXT
    body = _clean(_tess(_prep(img, (x, y, w, text_bottom(img) - y + 8), 2), 6))
    ind = _pick(_tess(_prep(img, BOX_INDUSTRY, 3), 7), INDUSTRIES)
    typ = _pick(_tess(_prep(img, BOX_TYPE, 3), 7), TYPES)
    typ = TYPE_TO_SITE.get(typ, typ)
    return {"body": body, "industry": ind, "accident_type": typ}
