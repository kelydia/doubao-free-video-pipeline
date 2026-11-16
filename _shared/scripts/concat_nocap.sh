#!/usr/bin/env bash
# 用法: 在任务目录根下执行 bash ../_shared/scripts/concat_nocap.sh （拼接 05_edit/norm_nocap/ 下的 7 镜）
set -e
FF=D:/Portable/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
OUT=${OUT:-$PWD/05_edit}
list=$OUT/list.txt
: > $list
for f in S1 S2 S3 S4 S5 S6 S7; do echo "file '$OUT/norm_nocap/$f.mp4'" >> $list; done
$FF -hide_banner -loglevel error -y -f concat -safe 0 -i $list -c:v libx264 -crf 18 -pix_fmt yuv420p -r 30 $OUT/picture_only_nocap.mp4
$FF -hide_banner -loglevel error -y -i $OUT/picture_only_nocap.mp4 -f lavfi -i "sine=frequency=220:duration=1" -shortest -c:v libx264 -crf 18 -pix_fmt yuv420p -r 30 $OUT/picture_only_nocap2.mp4
echo done
