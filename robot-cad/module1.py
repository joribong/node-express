"""모듈 1호 개념 형상 (본체 + 결합부 + 바퀴 + 덮개).

실행:  python robot-cad/module1.py
결과:  robot-cad/out/ 폴더에 STEP(3D), SVG·DXF(도면), CSV(부품표) 생성

치수는 모두 mm. 아래 Params 의 숫자만 바꾸면 형상 전체가 따라 바뀐다.
"""

from dataclasses import dataclass
from pathlib import Path
import csv

from build123d import (
    Align, Axis, Box, Compound, Cone, Cylinder, ExportDXF, ExportSVG,
    LineType, Location, Plane, Pos, Rot, Vector, export_step, fillet,
)

OUT = Path(__file__).parent / "out"


@dataclass
class Params:
    # 본체
    length: float = 120      # X 방향 길이
    width: float = 120       # Y 방향 폭
    height: float = 60       # Z 방향 높이
    corner_r: float = 6      # 세로 모서리 둥글기
    floor_t: float = 4       # 바닥 두께
    lid_t: float = 3         # 덮개 두께
    # 바퀴 (본체 안쪽에 숨겨서 옆면이 평평하게 유지됨 → 옆면끼리 결합 가능)
    wheel_r: float = 16
    wheel_w: float = 14
    wheel_x: float = 41      # 중심에서 바퀴 축까지 거리
    ground_clearance: float = 6
    well_gap: float = 1      # 바퀴와 바퀴집 사이 틈
    # 결합부 (암수 구분 없는 방식: 밖에서 볼 때 왼쪽은 핀, 오른쪽은 구멍)
    pin_dx: float = 15       # 면 중심에서 핀·구멍까지 좌우 거리
    pin_dz: float = 10       # 면 중심에서 위·아래 줄까지 거리
    pin_r: float = 4         # 핀 뿌리 반지름
    pin_tip_r: float = 2.5   # 핀 끝 반지름 (끝이 가늘어 스스로 중심이 맞음)
    pin_h: float = 7         # 핀 길이
    pin_clear: float = 0.3   # 핀과 구멍 사이 틈
    magnet_r: float = 6      # 중앙 자석(또는 잠금장치) 자리 반지름
    magnet_d: float = 3      # 자석 자리 깊이


def connector(p: Params):
    """결합부 한 면의 (더할 형상, 깎을 형상).

    기준 좌표: 면이 XY 평면, 바깥 방향이 +Z, 밖에서 볼 때 X가 오른쪽·Y가 위.
    """
    base = (Align.CENTER, Align.CENTER, Align.MIN)
    top = (Align.CENTER, Align.CENTER, Align.MAX)
    add, cut = [], []
    for dz in (p.pin_dz, -p.pin_dz):
        add.append(Pos(-p.pin_dx, dz, 0) * Cone(p.pin_r, p.pin_tip_r, p.pin_h, align=base))
        cut.append(Pos(p.pin_dx, dz, 0) *
                   Cylinder(p.pin_r + p.pin_clear, p.pin_h + 1, align=top))
    cut.append(Cylinder(p.magnet_r, p.magnet_d, align=top))
    return add, cut


def side_planes(p: Params):
    """옆면 4곳의 기준 평면 (바깥 방향 = 평면의 Z, 위쪽 = 평면의 Y)."""
    zc = p.height / 2
    up = Vector(0, 0, 1)
    faces = [
        (Vector(p.length / 2, 0, zc), Vector(1, 0, 0)),
        (Vector(-p.length / 2, 0, zc), Vector(-1, 0, 0)),
        (Vector(0, p.width / 2, zc), Vector(0, 1, 0)),
        (Vector(0, -p.width / 2, zc), Vector(0, -1, 0)),
    ]
    return [Plane(origin=o, x_dir=up.cross(n), z_dir=n) for o, n in faces]


def wheel_centers(p: Params):
    y = p.width / 2 - 2 - p.well_gap - p.wheel_w / 2
    z = p.wheel_r - p.ground_clearance
    return [Vector(sx * p.wheel_x, sy * y, z) for sx in (1, -1) for sy in (1, -1)]


def make_body(p: Params):
    bottom = (Align.CENTER, Align.CENTER, Align.MIN)
    body = Box(p.length, p.width, p.height, align=bottom)
    body = fillet(body.edges().filter_by(Axis.Z), p.corner_r)

    # 내부 공간 (배터리·기판 자리). 바퀴집과 결합부 뒤쪽은 살을 남긴다.
    well_w = p.wheel_w + 2 * p.well_gap
    cavity_x = p.length - 2 * (p.pin_h + 3)
    cavity_y = p.width - 2 * (2 + well_w + 4)
    body -= Pos(0, 0, p.floor_t) * Box(cavity_x, cavity_y, p.height, align=bottom)

    # 바퀴집
    for c in wheel_centers(p):
        body -= Pos(c) * Rot(90, 0, 0) * Cylinder(p.wheel_r + p.well_gap, well_w)

    # 옆면 4곳에 결합부
    add, cut = connector(p)
    for plane in side_planes(p):
        for s in add:
            body += plane.location * s
        for s in cut:
            body -= plane.location * s
    body.label = "body"
    return body


def make_lid(p: Params):
    lid = Box(p.length, p.width, p.lid_t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lid = fillet(lid.edges().filter_by(Axis.Z), p.corner_r)
    lid = Pos(0, 0, p.height) * lid
    lid.label = "lid"
    return lid


def make_wheels(p: Params):
    wheels = []
    for i, c in enumerate(wheel_centers(p), 1):
        w = Pos(c) * Rot(90, 0, 0) * Cylinder(p.wheel_r, p.wheel_w)
        w.label = f"wheel_{i}"
        wheels.append(w)
    return wheels


def make_module(p: Params, label="module1"):
    return Compound(label=label, children=[make_body(p), make_lid(p), *make_wheels(p)])


def _volume(result):
    """intersect 결과(없음·형상 하나·형상 여러 개)의 부피 합."""
    if not result:
        return 0.0
    return sum(x.volume for x in result) if isinstance(result, (list, tuple)) else result.volume


def check_docking(p: Params):
    """모듈 2개를 옆면끼리 붙였을 때 간섭이 없고 핀이 구멍에 들어가는지 확인."""
    a = make_body(p)
    for shift, name in ((Vector(p.length, 0, 0), "X"), (Vector(0, p.width, 0), "Y")):
        b = Pos(shift) * make_body(p)
        vol = _volume(a.intersect(b))
        assert vol < 1e-3, f"{name} 방향 결합 시 간섭 {vol:.2f} mm3"
        # 틈을 없앤 핀으로 다시 겹쳐 보면 핀 부피만큼 겹쳐야 한다(= 구멍 위치가 맞음)
        tight = Params(**{**p.__dict__, "pin_clear": -0.5})
        ov = _volume(a.intersect(Pos(shift) * make_body(tight)))
        assert ov > 1, f"{name} 방향에서 핀과 구멍 위치가 어긋남"
    return True


def export_views(shape, name: str, hidden_lines: bool = True):
    """정면·평면·측면 3면도 + 입체도를 SVG와 DXF로 저장 (치수선은 아직 없음)."""
    box = shape.bounding_box()
    gap = 30
    views = [  # (보는 방향, 위쪽 방향, 도면에서의 배치 이동)
        ((0, -1, 0), (0, 0, 1), (0, 0)),                                           # 정면
        ((0, 0, 1), (0, 1, 0), (0, -(box.size.Z / 2 + box.size.Y / 2 + gap))),     # 평면
        ((1, 0, 0), (0, 0, 1), (box.size.X / 2 + box.size.Y / 2 + gap, 0)),        # 측면
        ((0.6, -0.6, 0.5), (0, 0, 1), (box.size.X + box.size.Y + 2 * gap, -80)),   # 입체
    ]
    center = box.center()
    svg = ExportSVG(scale=1.5)
    dxf = ExportDXF()
    for ex in (svg, dxf):
        ex.add_layer("visible", line_weight=0.35)
        ex.add_layer("hidden", line_weight=0.18, line_type=LineType.ISO_DOT)
    for direction, up, (dx, dy) in views:
        origin = center + Vector(direction) * 1000   # 형상 중심을 정면으로 바라보게 한다
        visible, hidden = shape.project_to_viewport(origin, viewport_up=up, look_at=center)
        move = Location((dx, dy, 0))
        for ex in (svg, dxf):
            ex.add_shape([move * e for e in visible], layer="visible")
            if hidden_lines and dx < box.size.X + box.size.Y:   # 입체도에는 숨은선 생략
                ex.add_shape([move * e for e in hidden], layer="hidden")
    svg.write(str(OUT / f"{name}.svg"))
    dxf.write(str(OUT / f"{name}.dxf"))


def write_bom(p: Params, module):
    density = 1.05e-3  # g/mm3, ABS 수지 기준(개념 단계 추정)
    rows = [("품번", "품명", "수량", "재질(가정)", "부피_cm3", "추정무게_g", "비고")]
    parts = {c.label: c for c in module.children}
    def row(no, name, qty, key, note):
        v = parts[key].volume
        rows.append((no, name, qty, "ABS", f"{v / 1000:.1f}", f"{v * density * qty:.0f}", note))
    row("M1-001", "본체", 1, "body", "결합부 4면 일체형")
    row("M1-002", "덮개", 1, "lid", "")
    row("M1-003", "바퀴", 4, "wheel_1", "모터 미선정")
    rows.append(("M1-004", "결합용 자석 또는 잠금장치", 4, "미정", "", "", f"자리 지름 {2 * p.magnet_r:g} x 깊이 {p.magnet_d:g}"))
    with open(OUT / "module1_bom.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    return rows


def main():
    p = Params()
    OUT.mkdir(exist_ok=True)
    check_docking(p)
    print("결합 검사 통과: X·Y 방향 모두 간섭 없음, 핀-구멍 위치 일치")

    module = make_module(p)
    export_step(module, str(OUT / "module1.step"))
    export_views(module, "module1_views")

    # 합체 예시: 2 x 2 로 붙인 4대
    cluster = Compound(label="cluster_2x2", children=[
        Pos(i * p.length, j * p.width, 0) * make_module(p, f"module_{i}{j}")
        for i in (0, 1) for j in (0, 1)])
    export_step(cluster, str(OUT / "cluster_2x2.step"))
    export_views(cluster, "cluster_2x2_views", hidden_lines=False)

    for r in write_bom(p, module):
        print(" | ".join(str(x) for x in r))
    bb = module.bounding_box()
    print(f"외형: {bb.size.X:.0f} x {bb.size.Y:.0f} x {bb.size.Z:.0f} mm (핀·바퀴 포함)")


if __name__ == "__main__":
    main()
