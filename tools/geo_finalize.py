"""지도 경계 3단계: mapshaper 가 합친 결과를 사이트용 파일로 저장.

  python tools/geo_finalize.py sido.geojson sgg.geojson "출처 표기 문구"
출력: docs/geo/kr-sido.js, docs/geo/kr-sigungu.js
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from collector.region import SIDO_FULL  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GEO = os.path.join(ROOT, "docs", "geo")


def rnd(coords, nd=4):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [rnd(c, nd) for c in coords]


def finalize(sido_fc, sgg_fc, credit):
    sido = {"type": "FeatureCollection", "features": []}
    for ft in sido_fc["features"]:
        sd = (ft.get("properties") or {}).get("SD")
        if sd in SIDO_FULL and ft.get("geometry"):
            sido["features"].append({"type": "Feature", "properties": {"name": SIDO_FULL[sd]},
                                     "geometry": {"type": ft["geometry"]["type"], "coordinates": rnd(ft["geometry"]["coordinates"])}})
    sgg = {"type": "FeatureCollection", "features": []}
    for ft in sgg_fc["features"]:
        p = ft.get("properties") or {}
        sd, nm = p.get("SD"), p.get("SGG")
        if not nm and p.get("KEY"):
            sd, nm = p["KEY"].split("|", 1)
        if sd in SIDO_FULL and nm and ft.get("geometry"):
            sgg["features"].append({"type": "Feature", "properties": {"sido": sd, "name": nm},
                                    "geometry": {"type": ft["geometry"]["type"], "coordinates": rnd(ft["geometry"]["coordinates"])}})
    return sido, sgg


def write(name, key, fc, credit):
    os.makedirs(GEO, exist_ok=True)
    path = os.path.join(GEO, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"window.JDMAP_GEO_SOURCE = {json.dumps(credit, ensure_ascii=False)};\n")
        f.write(f'Highcharts.maps["{key}"] = ')
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    return path, os.path.getsize(path)


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        sido_fc = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        sgg_fc = json.load(f)
    credit = sys.argv[3] if len(sys.argv) > 3 else "행정구역 경계 공개 데이터"
    sido, sgg = finalize(sido_fc, sgg_fc, credit)
    if len(sido["features"]) < 17:
        sys.exit(f"오류: 시도 도형이 {len(sido['features'])}개입니다 (17개 필요).")
    for name, key, fc in (("kr-sido.js", "countries/kr/kr-all", sido), ("kr-sigungu.js", "countries/kr/kr-sigungu", sgg)):
        p, size = write(name, key, fc, credit)
        print(f"저장: {os.path.relpath(p, ROOT)} · {len(fc['features'])}개 · {size // 1024}KB")


if __name__ == "__main__":
    main()
