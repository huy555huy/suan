#!/bin/bash
# 下载 78 张 RWS 韦特塔罗到 web/static/img/tarot/
# 来源：Wikimedia Commons（Pamela Colman Smith 1909 绘，2022 进入美国公有领域）
# 总大小约 70 MB · 仓库不入库这些图，clone 后跑此脚本拉一次即可
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
DIR="$PROJECT_ROOT/web/static/img/tarot"
mkdir -p "$DIR"
cd "$DIR" || exit 1
echo "→ 目标目录：$DIR"

dl() {
  local src="$1" dst="$2"
  local url="https://commons.wikimedia.org/wiki/Special:FilePath/${src}"
  if [ -f "$dst" ] && [ "$(/usr/bin/stat -f '%z' "$dst")" -gt 50000 ]; then
    return 0  # 已存在且非占位
  fi
  /usr/bin/curl -sL -o "$dst.tmp" "$url" --max-filesize 2500000
  local sz=$(/usr/bin/stat -f '%z' "$dst.tmp" 2>/dev/null || echo 0)
  if [ "$sz" -gt 50000 ] && file "$dst.tmp" | grep -q JPEG; then
    /bin/mv "$dst.tmp" "$dst"
    echo "  ✓ $dst ($((sz/1024)) KB)"
  else
    /bin/rm -f "$dst.tmp"
    echo "  ✗ $dst FAIL ($src)"
    return 1
  fi
}

# 大阿卡纳 22 张（实际 Wikimedia 命名带 underscore）
echo "=== 大阿卡纳 22 张 ==="
dl "RWS_Tarot_00_Fool.jpg" "major_00_fool.jpg"
dl "RWS_Tarot_01_Magician.jpg" "major_01_magician.jpg"
dl "RWS_Tarot_02_High_Priestess.jpg" "major_02_priestess.jpg"
dl "RWS_Tarot_03_Empress.jpg" "major_03_empress.jpg"
dl "RWS_Tarot_04_Emperor.jpg" "major_04_emperor.jpg"
dl "RWS_Tarot_05_Hierophant.jpg" "major_05_hierophant.jpg"
dl "RWS_Tarot_06_Lovers.jpg" "major_06_lovers.jpg"
dl "RWS_Tarot_07_Chariot.jpg" "major_07_chariot.jpg"
dl "RWS_Tarot_08_Strength.jpg" "major_08_strength.jpg"
dl "RWS_Tarot_09_Hermit.jpg" "major_09_hermit.jpg"
dl "RWS_Tarot_10_Wheel_of_Fortune.jpg" "major_10_wheel.jpg"
dl "RWS_Tarot_11_Justice.jpg" "major_11_justice.jpg"
dl "RWS_Tarot_12_Hanged_Man.jpg" "major_12_hanged.jpg"
dl "RWS_Tarot_13_Death.jpg" "major_13_death.jpg"
dl "RWS_Tarot_14_Temperance.jpg" "major_14_temperance.jpg"
dl "RWS_Tarot_15_Devil.jpg" "major_15_devil.jpg"
dl "RWS_Tarot_16_Tower.jpg" "major_16_tower.jpg"
dl "RWS_Tarot_17_Star.jpg" "major_17_star.jpg"
dl "RWS_Tarot_18_Moon.jpg" "major_18_moon.jpg"
dl "RWS_Tarot_19_Sun.jpg" "major_19_sun.jpg"
dl "RWS_Tarot_20_Judgement.jpg" "major_20_judgement.jpg"
dl "RWS_Tarot_21_World.jpg" "major_21_world.jpg"

echo
echo "=== 小阿卡纳 4 × 14 = 56 张 ==="
for suit_pair in "Wands:wands" "Cups:cups" "Swords:swords" "Pents:pents"; do
  src_prefix="${suit_pair%%:*}"
  dst_prefix="${suit_pair##*:}"
  for n in 01 02 03 04 05 06 07 08 09 10 11 12 13 14; do
    dl "${src_prefix}${n}.jpg" "${dst_prefix}_${n}.jpg"
  done
done

echo
echo "=== 总文件数 / 总大小 ==="
find "$DIR" -maxdepth 1 -name '*.jpg' | wc -l
du -sh "$DIR"
