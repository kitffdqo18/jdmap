#!/bin/sh
# 지도 경계 만들기 (GitHub Actions '지도 경계 만들기'가 실행)
#   sh tools/build_geo.sh <원본 GeoJSON 주소> "<출처 표기>"
# 1) 원본 내려받기 → 2) 시도·시군구 키 붙이기 → 3) mapshaper 로 합치고 단순화 → 4) 사이트용 파일 저장
set -e
URL="$1"
CREDIT="${2:-행정구역 경계 공개 데이터}"
SGG_SIMPLIFY="${SGG_SIMPLIFY:-4%}"
SIDO_SIMPLIFY="${SIDO_SIMPLIFY:-1.5%}"
W=$(mktemp -d)

echo "1) 원본 내려받기: $URL"
curl -fL --retry 3 -o "$W/raw.geojson" "$URL"
ls -l "$W/raw.geojson"

echo "2) 시도·시군구 키 붙이기"
python tools/geo_prepare.py "$W/raw.geojson" "$W/prepared.geojson"

echo "3) 경계 합치기·단순화 (mapshaper)"
npx --yes mapshaper@0.6 "$W/prepared.geojson" -dissolve2 KEY copy-fields=SD,SGG \
  -simplify "$SGG_SIMPLIFY" keep-shapes -o format=geojson precision=0.0001 "$W/sgg.geojson"
npx --yes mapshaper@0.6 "$W/prepared.geojson" -dissolve2 SD \
  -simplify "$SIDO_SIMPLIFY" keep-shapes -o format=geojson precision=0.0001 "$W/sido.geojson"

echo "4) 사이트용 파일 저장"
python tools/geo_finalize.py "$W/sido.geojson" "$W/sgg.geojson" "$CREDIT"
rm -rf "$W"
