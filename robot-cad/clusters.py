"""합체 형태 생성: 같은 모듈 여러 대를 옆면끼리 붙인 조합.

실행:  python robot-cad/clusters.py
결과:  out/cluster_<이름>.step / .glb / _views.svg, out/clusters.csv, out/clusters.json

힘 계산은 바퀴가 미끄러지기 직전까지 낼 수 있는 힘(마찰 한계) 기준의 단순 추정이다.
모터 힘이 그보다 작으면 실제 값은 더 낮다. 시뮬레이션(sim/)으로 따로 확인한다.
"""

import copy
import csv
import json

from build123d import Compound, Pos, export_step

import module1 as m

G = 9.81
MU_WHEEL = 0.8     # 고무 바퀴와 바닥 사이 마찰계수 (가정)
MU_LOAD = 0.5      # 미는 짐과 바닥 사이 마찰계수 (가정)

# 이름: (설명, 모듈이 놓이는 격자 칸 목록 (x칸, y칸))
SHAPES = {
    "single":   ("단독 1대", [(0, 0)]),
    "line4":    ("일렬 4대 (좁은 통로를 지나며 길게 연결)", [(0, 0), (1, 0), (2, 0), (3, 0)]),
    "square4":  ("사각 2 x 2 (짐을 올리는 받침, 밀기)", [(0, 0), (1, 0), (0, 1), (1, 1)]),
    "lshape4":  ("ㄴ자 4대 (모서리를 감싸 밀기)", [(0, 0), (0, 1), (1, 0), (2, 0)]),
    "square9":  ("사각 3 x 3 (큰 받침)", [(i, j) for i in range(3) for j in range(3)]),
}


def neighbours(cells):
    s = set(cells)
    return [(a, (a[0] + dx, a[1] + dy)) for a in cells for dx, dy in ((1, 0), (0, 1)) if (a[0] + dx, a[1] + dy) in s]


def build_cluster(p, name, parts, body):
    desc, cells = SHAPES[name]
    # 붙는 면마다 간섭 검사 (본체끼리)
    for a, b in neighbours(cells):
        pa = Pos(a[0] * p.length, a[1] * p.width, 0) * body
        pb = Pos(b[0] * p.length, b[1] * p.width, 0) * body
        vol = m._volume(pa.intersect(pb))
        assert vol < 1e-3, f"{name}: {a}-{b} 결합면 간섭 {vol:.2f} mm3"
    children = []
    for i, (cx, cy) in enumerate(cells):
        mod_parts = [(k, Pos(cx * p.length, cy * p.width, 0) * copy.copy(s)) for k, s in parts]
        children.append(m.make_module(p, label=f"module_{i + 1}", parts=mod_parts))
    cluster = Compound(label=f"cluster_{name}", children=children)
    export_step(cluster, str(m.OUT / f"cluster_{name}.step"))
    m.export_glb(cluster, m.OUT / f"cluster_{name}.glb")
    m.export_views(cluster, f"cluster_{name}_views", hidden_lines=False)

    n = len(cells)
    mass_g, _ = m.mass_summary(parts)
    total_kg = n * mass_g / 1000
    push_n = MU_WHEEL * total_kg * G
    bb = cluster.bounding_box()
    return {
        "name": name, "description": desc, "modules": n, "cells": cells,
        "joints": len(neighbours(cells)),
        "size_mm": [round(bb.size.X), round(bb.size.Y), round(bb.size.Z)],
        "mass_kg": round(total_kg, 2),
        "max_push_N": round(push_n, 1),
        "max_load_kg": round(push_n / (MU_LOAD * G), 1),
        "top_area_cm2": round(n * p.length * p.width / 100),
    }


def main():
    p = m.Params()
    m.OUT.mkdir(exist_ok=True)
    parts = m.make_parts(p, locked=True)      # 합체 상태이므로 잠금 볼트를 잠근 모습으로
    body = parts[0][1]
    results = [build_cluster(p, name, parts, body) for name in SHAPES]

    (m.OUT / "clusters.json").write_text(json.dumps(
        {"assumptions": {"mu_wheel": MU_WHEEL, "mu_load": MU_LOAD}, "clusters": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    head = ("이름", "설명", "모듈 수", "결합면 수", "크기_mm", "무게_kg", "최대 미는 힘_N", "밀 수 있는 짐_kg", "윗면 넓이_cm2")
    with open(m.OUT / "clusters.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in results:
            w.writerow((r["name"], r["description"], r["modules"], r["joints"], " x ".join(map(str, r["size_mm"])),
                        r["mass_kg"], r["max_push_N"], r["max_load_kg"], r["top_area_cm2"]))
    print("합체 형태 생성 완료, 결합면 간섭 없음")
    for r in results:
        print(f"  {r['name']:8s} {r['modules']}대  {r['size_mm']} mm  {r['mass_kg']} kg  "
              f"미는 힘 {r['max_push_N']} N  짐 {r['max_load_kg']} kg")


if __name__ == "__main__":
    main()
