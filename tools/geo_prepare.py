"""지도 경계 1단계: 행정동(또는 시군구) 경계 GeoJSON 에 시도·시군구 키를 붙인다.

  python tools/geo_prepare.py 원본.geojson prepared.geojson

지원하는 원본 속성 (자동 인식)
- 행정동 경계 (예: vuski/admdongkor):  sidonm, sggnm  또는  adm_nm('서울특별시 종로구 사직동')
- 통계청 SGIS 시군구 경계:              SIG_CD(행정구역코드), SIG_KOR_NM
일반구(수원시 장안구 등)는 시 단위로 합친다. KEEP_GU=1 이면 구까지 유지.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from collector.region import SIDO_ALIASES  # noqa: E402

CODE_TO_SIDO = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산",
                "36": "세종", "41": "경기", "42": "강원", "51": "강원", "43": "충북", "44": "충남", "45": "전북",
                "52": "전북", "46": "전남", "47": "경북", "48": "경남", "50": "제주"}
METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산"}
_GU = re.compile(r"^(.+?시)\s*(.+구)$")


def sido_short(v):
    v = (v or "").strip()
    for k, aliases in SIDO_ALIASES.items():
        if v == k or v in aliases:
            return k
    return None


def sgg_display(sd, name, keep_gu=False):
    name = re.sub(r"\s+", " ", (name or "").strip())
    if sd == "세종":
        return "세종시"
    if sd not in METRO and not keep_gu:
        m = _GU.match(name)
        if m:
            return m.group(1)
    return name


def keys_of(props, keep_gu=False):
    """(시도 약칭, 시군구 표시명) 또는 (None, None)."""
    p = props or {}
    sd = sido_short(p.get("sidonm") or p.get("CTP_KOR_NM") or p.get("SIDO_NM") or "")
    sgg = p.get("sggnm") or p.get("SIG_KOR_NM") or p.get("SGG_NM")
    code = str(p.get("SIG_CD") or p.get("sgg") or p.get("adm_cd2") or p.get("adm_cd") or "")
    if not sd and code[:2] in CODE_TO_SIDO:
        sd = CODE_TO_SIDO[code[:2]]
    if (not sd or not sgg) and p.get("adm_nm"):
        parts = str(p["adm_nm"]).split()
        if len(parts) >= 2:
            sd = sd or sido_short(parts[0])
            if not sgg:
                sgg = parts[1]
                if len(parts) >= 4 and parts[1].endswith("시") and parts[2].endswith("구"):
                    sgg = parts[1] + " " + parts[2]
    if sd == "세종":
        return sd, "세종시"
    if not sd or not sgg:
        return None, None
    return sd, sgg_display(sd, sgg, keep_gu)


def prepare(gj, keep_gu=False):
    out, skipped = [], 0
    for ft in gj.get("features", []):
        sd, sgg = keys_of(ft.get("properties"), keep_gu)
        if not (sd and sgg and ft.get("geometry")):
            skipped += 1
            continue
        out.append({"type": "Feature", "properties": {"SD": sd, "SGG": sgg, "KEY": f"{sd}|{sgg}"}, "geometry": ft["geometry"]})
    return {"type": "FeatureCollection", "features": out}, skipped


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        gj = json.load(f)
    fc, skipped = prepare(gj, keep_gu=os.environ.get("KEEP_GU") == "1")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    sidos = {x["properties"]["SD"] for x in fc["features"]}
    sggs = {x["properties"]["KEY"] for x in fc["features"]}
    print(f"준비: 도형 {len(fc['features'])}개 · 시도 {len(sidos)}개 · 시군구 {len(sggs)}개 · 제외 {skipped}개")
    if len(sidos) < 17:
        sys.exit(f"오류: 시도가 {len(sidos)}개뿐입니다. 원본 속성 이름을 확인하세요 (예: sidonm, sggnm, adm_nm).")


if __name__ == "__main__":
    main()
