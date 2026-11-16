#!/bin/sh
# 설계 결과물을 처음부터 다시 만든다.  실행: sh robot-cad/build_all.sh
set -e
cd "$(dirname "$0")"
python3 module1.py          # 모듈 1대: 3D 파일, 형상 확인용 도면, 부품표
python3 clusters.py         # 합체 형태 5가지
MUJOCO_GL=egl python3 sim/push_sim.py   # 시뮬레이션 영상과 결과표
python3 joint_loads.py      # 잠금장치가 버텨야 하는 힘과 버틸 수 있는 힘
python3 drawing.py          # 치수 도면 (SVG, DXF)
node make_pdf.js            # 치수 도면 PDF


