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

BASE_W, BASE_H = 992, 1403
# (x, y, 가로, 세로) — 기준 크기 좌표. 그림 크기가 다르면 비율로 맞춘다.
BOX_TEXT = (75, 430, 850, 190)
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


def _tess(img, psm):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        img.save(f.name)
        r = subprocess.run(["tesseract", f.name, "stdout", "-l", "kor", "--psm", str(psm)],
                           capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "ignore")


def _clean(s):
    s = re.sub(r"[\r\n]+", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lstrip("'‘’`\"| ").strip()
    # 날짜 앞의 '26년 → 2026년 (연도 인식을 돕기 위해)
    s = re.sub(r"^[‘’'`]?\s*(\d{2})\s*년", lambda m: f"20{m.group(1)}년", s)
    # 'N일(요일)' 부분이 깨져도 날짜·시각이 읽히도록 정리: 28일기 → 28일, 24일퇴 → 24일
    s = re.sub(r"(\d{1,2})\s*일\s*\(?[^\d\s]{0,2}\)?\s*(?=\d{1,2}\s*[:시])", r"\1일 ", s)
    return s


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
    body = _clean(_tess(_prep(img, BOX_TEXT, 2), 6))
    ind = _pick(_tess(_prep(img, BOX_INDUSTRY, 3), 7), INDUSTRIES)
    typ = _pick(_tess(_prep(img, BOX_TYPE, 3), 7), TYPES)
    typ = TYPE_TO_SITE.get(typ, typ)
    return {"body": body, "industry": ind, "accident_type": typ}
