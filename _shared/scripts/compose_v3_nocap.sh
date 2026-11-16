#!/usr/bin/env bash
# 7 镜合成 v3：源为豆包原始片 720x1280 → 放大到 1080x1920，**不叠花字**（纯净版）
# 用法: bash scripts/compose_v3_nocap.sh
set -e
FF=D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
ROOT=${ROOT:-$PWD}
IN=${IN:-$ROOT/03_clips}
OUT=${OUT:-$ROOT/05_edit}
mkdir -p "$OUT/norm_nocap"

# $1 源名 $2 目标名 $3 时长
norm() {
  local src=$1 name=$2 dur=$3
  "$FF" -hide_banner -loglevel error -y -i "$IN/$src.mp4" \
    -vf "trim=0:$dur,setpts=PTS-STARTPTS,scale=1080:1920:flags=lanczos,format=yuv420p" \
    -an -r 30 -t "$dur" -c:v libx264 -crf 17 -pix_fmt yuv420p "$OUT/norm_nocap/$name.mp4"
  echo "norm $name ($dur s) ok"
}

norm S1 S1 5
norm S2 S2 4
norm S3 S3 6
norm S4 S4 4
norm S5 S5 6
norm S6 S6 5
norm S7 S7 4
echo done
