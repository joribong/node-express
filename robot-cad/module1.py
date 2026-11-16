"""모듈 1호 설계 (본체 + 결합부 + 구동부 + 전원 + 기판).

실행:  python robot-cad/module1.py
결과:  robot-cad/out/ 폴더에 STEP·GLB(3D), SVG·DXF(도면), CSV(부품표) 생성

치수는 모두 mm. 아래 Params 의 숫자만 바꾸면 형상 전체가 따라 바뀐다.
구매 부품(모터·배터리·기판)은 시중 규격품의 대표 치수로 자리만 잡은 것이다.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import copy
import csv
import json
import sys

from build123d import (
    Align, Axis, Box, Color, Compound, Cone, Cylinder, ExportDXF, ExportSVG,
    LineType, Location, Plane, Pos, Rot, Vector, export_gltf, export_step, fillet,
)

OUT = Path(__file__).parent / "out"
BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
TOP = (Align.CENTER, Align.CENTER, Align.MAX)


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
    well_wall: float = 4     # 바퀴집과 내부 공간 사이 벽 두께
    # 결합부 (암수 구분 없는 방식: 밖에서 볼 때 왼쪽은 핀, 오른쪽은 구멍)
    pin_dx: float = 15       # 면 중심에서 핀·구멍까지 좌우 거리
    pin_dz: float = 10       # 면 중심에서 위·아래 줄까지 거리
    pin_r: float = 4         # 핀 뿌리 반지름
    pin_tip_r: float = 2.5   # 핀 끝 반지름 (끝이 가늘어 스스로 중심이 맞음)
    pin_h: float = 7         # 핀 길이
    pin_clear: float = 0.3   # 핀과 구멍 사이 틈
    magnet_r: float = 6      # 중앙 자석(또는 잠금장치) 자리 반지름
    magnet_d: float = 3      # 자석 자리 깊이
    # 전기 접점 (왼쪽 스프링 핀, 오른쪽 접촉판. 윗줄 +, 아랫줄 -)
    contact_dx: float = 6
    contact_dz: float = 20
    pogo_r: float = 1.2
    pogo_len: float = 6
    pogo_out: float = 0.8    # 스프링 핀이 면 밖으로 나온 길이
    pad_r: float = 2.4
    pad_t: float = 0.5
    pad_recess: float = 1.0  # 접촉판 자리 깊이 (결합 시 스프링 핀이 0.3 눌림)
    # 모터 (N20 급 소형 기어모터 대표 치수)
    motor_w: float = 12      # X 방향
    motor_h: float = 10      # Z 방향
    motor_len: float = 24    # 모터 + 감속기 길이
    shaft_r: float = 1.5
    shaft_len: float = 12
    # 배터리 (18650 셀 2개)
    cell_r: float = 9
    cell_len: float = 65
    cell_dy: float = 10      # 중심에서 셀 축까지 거리
    # 기판
    pcb_l: float = 70
    pcb_w: float = 60
    pcb_t: float = 1.6
    pcb_z: float = 36        # 기판 아랫면 높이
    standoff_r: float = 2.5


# ---------------------------------------------------------------- 위치 계산

def well_width(p):
    return p.wheel_w + 2 * p.well_gap


def cavity_size(p):
    """내부 공간의 X, Y 크기."""
    return (p.length - 2 * (p.pin_h + 3),
            p.width - 2 * (2 + well_width(p) + p.well_wall))


def wheel_centers(p):
    y = p.width / 2 - 2 - p.well_gap - p.wheel_w / 2
    z = p.wheel_r - p.ground_clearance
    return [Vector(sx * p.wheel_x, sy * y, z) for sx in (1, -1) for sy in (1, -1)]


def side_planes(p):
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


def standoff_xy(p):
    return [(sx * (p.pcb_l / 2 - 4), sy * (p.pcb_w / 2 - 4)) for sx in (1, -1) for sy in (1, -1)]


# ---------------------------------------------------------------- 부품

def connector(p):
    """결합부 한 면의 (더할 형상, 깎을 형상).

    기준 좌표: 면이 XY 평면, 바깥 방향이 +Z, 밖에서 볼 때 X가 오른쪽·Y가 위.
    """
    add, cut = [], []
    for dz in (p.pin_dz, -p.pin_dz):
        add.append(Pos(-p.pin_dx, dz, 0) * Cone(p.pin_r, p.pin_tip_r, p.pin_h, align=BOTTOM))
        cut.append(Pos(p.pin_dx, dz, 0) * Cylinder(p.pin_r + p.pin_clear, p.pin_h + 1, align=TOP))
    cut.append(Cylinder(p.magnet_r, p.magnet_d, align=TOP))
    for dz in (p.contact_dz, -p.contact_dz):
        cut.append(Pos(-p.contact_dx, dz, 0) * Cylinder(p.pogo_r, p.pogo_len - p.pogo_out, align=TOP))
        cut.append(Pos(p.contact_dx, dz, 0) * Cylinder(p.pad_r + 0.1, p.pad_recess, align=TOP))
    return add, cut


def make_body(p):
    body = Box(p.length, p.width, p.height, align=BOTTOM)
    body = fillet(body.edges().filter_by(Axis.Z), p.corner_r)

    # 내부 공간 (배터리·기판 자리). 바퀴집과 결합부 뒤쪽은 살을 남긴다.
    cx, cy = cavity_size(p)
    body -= Pos(0, 0, p.floor_t) * Box(cx, cy, p.height, align=BOTTOM)

    # 기판 받침 기둥 (본체와 한 덩어리)
    for x, y in standoff_xy(p):
        body += Pos(x, y, p.floor_t) * Cylinder(p.standoff_r, p.pcb_z - p.floor_t, align=BOTTOM)

    # 바퀴집과 모터축 구멍
    for c in wheel_centers(p):
        body -= Pos(c) * Rot(90, 0, 0) * Cylinder(p.wheel_r + p.well_gap, well_width(p))
        body -= Pos(c.X, 0, c.Z) * Rot(90, 0, 0) * Cylinder(p.shaft_r + 0.3, p.width - 6)

    # 옆면 4곳에 결합부
    add, cut = connector(p)
    for plane in side_planes(p):
        for s in add:
            body += plane.location * s
        for s in cut:
            body -= plane.location * s
    return body


def make_lid(p):
    lid = Box(p.length, p.width, p.lid_t, align=BOTTOM)
    lid = fillet(lid.edges().filter_by(Axis.Z), p.corner_r)
    return Pos(0, 0, p.height) * lid


def make_wheel(p, c):
    w = Rot(90, 0, 0) * (Cylinder(p.wheel_r, p.wheel_w) - Cylinder(p.shaft_r, p.wheel_w))
    return Pos(c) * w


def make_motor(p, c):
    """바퀴 하나를 직접 돌리는 기어모터. 감속기 면이 바퀴집 벽에 붙는다."""
    _, cy = cavity_size(p)
    sy = 1 if c.Y > 0 else -1
    y_face = sy * cy / 2
    body = Pos(c.X, y_face - sy * p.motor_len / 2, c.Z) * Box(p.motor_w, p.motor_len, p.motor_h)
    shaft = Pos(c.X, y_face + sy * p.shaft_len / 2, c.Z) * Rot(90, 0, 0) * Cylinder(p.shaft_r, p.shaft_len)
    return body + shaft


def make_cell(p, sy):
    z = p.floor_t + p.cell_r + 0.5
    return Pos(0, sy * p.cell_dy, z) * Rot(0, 90, 0) * Cylinder(p.cell_r, p.cell_len)


def make_pcb(p):
    return Pos(0, 0, p.pcb_z) * Box(p.pcb_l, p.pcb_w, p.pcb_t, align=BOTTOM)


def make_face_parts(p):
    """옆면마다 들어가는 자석·스프링 핀·접촉판."""
    magnets, pogos, pads = [], [], []
    for plane in side_planes(p):
        loc = plane.location
        magnets.append(loc * Cylinder(p.magnet_r - 0.1, p.magnet_d, align=TOP))
        for dz in (p.contact_dz, -p.contact_dz):
            pogos.append(loc * Pos(-p.contact_dx, dz, p.pogo_out) * Cylinder(p.pogo_r, p.pogo_len, align=TOP))
            pads.append(loc * Pos(p.contact_dx, dz, -p.pad_recess) * Cylinder(p.pad_r, p.pad_t, align=BOTTOM))
    return magnets, pogos, pads


# 부품 종류별 정보: 품번, 품명, 색, 무게 계산 방식, 소량 구매 단가(달러, 조사 메모 기준 추정)
# 무게: ("density", g/mm3) 는 부피로 계산, ("each", g) 는 규격품 대표 무게
KINDS = {
    "body":   ("M1-001", "본체",            (0.80, 0.82, 0.85), ("density", 1.05e-3), None,  "ABS 수지, 결합 핀·기판 받침 일체형"),
    "lid":    ("M1-002", "덮개",            (0.25, 0.45, 0.80), ("density", 1.05e-3), None,  "ABS 수지"),
    "wheel":  ("M1-003", "바퀴",            (0.15, 0.15, 0.15), ("density", 1.10e-3), None,  "수지 휠 + 고무 타이어"),
    "motor":  ("M1-101", "기어모터 (N20 급)", (0.75, 0.60, 0.20), ("each", 10.0),       10.0,  "바퀴마다 1개, 연장축 필요"),
    "cell":   ("M1-102", "배터리 셀 18650",  (0.20, 0.65, 0.35), ("each", 46.0),       5.0,   "2개 직렬 7.4V 가정"),
    "pcb":    ("M1-103", "제어 기판",        (0.10, 0.45, 0.25), ("each", 25.0),       15.0,  "ESP32 급 + 모터 드라이버 + 충전 회로"),
    "magnet": ("M1-104", "결합용 자석",      (0.70, 0.70, 0.75), ("density", 7.5e-3),  1.0,   "지름 12 x 3, 잠금장치로 교체 예정"),
    "pogo":   ("M1-105", "스프링 접점 핀",   (0.85, 0.70, 0.25), ("each", 0.3),        0.4,   "면마다 +, - 각 1개"),
    "pad":    ("M1-106", "접촉판",           (0.85, 0.70, 0.25), ("each", 0.1),        0.1,   "면마다 +, - 각 1개"),
}


def make_parts(p):
    """[(종류, 형상)] 목록."""
    parts = [("body", make_body(p)), ("lid", make_lid(p))]
    for c in wheel_centers(p):
        parts.append(("wheel", make_wheel(p, c)))
        parts.append(("motor", make_motor(p, c)))
    parts += [("cell", make_cell(p, 1)), ("cell", make_cell(p, -1)), ("pcb", make_pcb(p))]
    magnets, pogos, pads = make_face_parts(p)
    parts += [("magnet", m) for m in magnets] + [("pogo", g) for g in pogos] + [("pad", d) for d in pads]
    return parts


def make_module(p, label="module1", parts=None):
    children, count = [], {}
    for kind, shape in parts or make_parts(p):
        count[kind] = count.get(kind, 0) + 1
        shape.label = f"{kind}_{count[kind]}"
        shape.color = Color(*KINDS[kind][2])
        children.append(shape)
    return Compound(label=label, children=children)


# ---------------------------------------------------------------- 검사와 계산

def _volume(result):
    """intersect 결과(없음·형상 하나·형상 여러 개)의 부피 합."""
    if not result:
        return 0.0
    return sum(x.volume for x in result) if isinstance(result, (list, tuple)) else result.volume


def _boxes_overlap(a, b):
    return all(lo1 < hi2 and lo2 < hi1 for lo1, hi1, lo2, hi2 in
               zip(tuple(a.min), tuple(a.max), tuple(b.min), tuple(b.max)))


def check_internal(parts):
    """한 모듈 안에서 부품끼리 겹치는 곳이 없는지 확인."""
    boxes = [s.bounding_box() for _, s in parts]
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            if not _boxes_overlap(boxes[i], boxes[j]):
                continue
            vol = _volume(parts[i][1].intersect(parts[j][1]))
            assert vol < 1e-2, f"부품 간섭: {parts[i][0]} 와 {parts[j][0]} 가 {vol:.2f} mm3 겹침"
    return True


def check_docking(p):
    """모듈 2개를 옆면끼리 붙였을 때 간섭이 없고 핀이 구멍에 들어가는지 확인."""
    a = make_body(p)
    for shift, name in ((Vector(p.length, 0, 0), "X"), (Vector(0, p.width, 0), "Y")):
        vol = _volume(a.intersect(Pos(shift) * make_body(p)))
        assert vol < 1e-3, f"{name} 방향 결합 시 간섭 {vol:.2f} mm3"
        # 틈을 없앤 구멍으로 다시 겹쳐 보면 핀 부피만큼 겹쳐야 한다(= 구멍 위치가 맞음)
        tight = Params(**{**asdict(p), "pin_clear": -0.5})
        ov = _volume(a.intersect(Pos(shift) * make_body(tight)))
        assert ov > 1, f"{name} 방향에서 핀과 구멍 위치가 어긋남"
    return True


def part_mass(kind, shape):
    how, value = KINDS[kind][3]
    return shape.volume * value if how == "density" else value


def mass_summary(parts):
    """(총 무게 g, 무게중심 Vector)."""
    total, moment = 0.0, Vector(0, 0, 0)
    for kind, shape in parts:
        m = part_mass(kind, shape)
        total += m
        moment += shape.center() * m
    return total, moment / total


# ---------------------------------------------------------------- 내보내기

def export_views(shape, name, hidden_lines=True):
    """정면·평면·측면 3면도 + 입체도를 SVG와 DXF로 저장 (치수 없는 형상 확인용)."""
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


def bom_rows(parts):
    rows = [("품번", "품명", "수량", "개당무게_g", "무게합_g", "개당단가_USD(추정)", "금액_USD(추정)", "비고")]
    seen = {}
    for kind, shape in parts:
        seen.setdefault(kind, []).append(shape)
    total_m = total_c = 0.0
    for kind, shapes in seen.items():
        no, name, _, _, price, note = KINDS[kind]
        qty = len(shapes)
        each = part_mass(kind, shapes[0])
        cost = price * qty if price is not None else None
        total_m += each * qty
        total_c += cost or 0
        rows.append((no, name, qty, f"{each:.1f}", f"{each * qty:.0f}",
                     "" if price is None else f"{price:.1f}", "" if cost is None else f"{cost:.1f}", note))
    rows.append(("", "합계", "", "", f"{total_m:.0f}", "", f"{total_c:.1f}", "제작품(본체·덮개·바퀴) 가공비는 미포함"))
    return rows


def write_bom(parts):
    rows = bom_rows(parts)
    with open(OUT / "module1_bom.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    return rows


def build(p, out=OUT, drawings=True):
    """모듈 한 대를 만들고 검사한 뒤 파일로 내보낸다. 요약 정보를 돌려준다."""
    out.mkdir(parents=True, exist_ok=True)
    parts = make_parts(p)
    check_internal(parts)
    check_docking(p)
    module = make_module(p, parts=parts)
    export_step(module, str(out / "module1.step"))
    export_gltf(module, str(out / "module1.glb"), binary=True)
    if drawings:
        export_views(module, "module1_views")
        # 덮개를 벗긴 내부 배치도
        inside = Compound(children=[copy.copy(s) for k, s in parts if k != "lid"])
        export_views(inside, "module1_inside_views", hidden_lines=False)
    mass, cog = mass_summary(parts)
    bb = module.bounding_box()
    info = {
        "mass_g": round(mass),
        "center_of_mass_mm": [round(v, 1) for v in tuple(cog)],
        "outer_size_mm": [round(bb.size.X), round(bb.size.Y), round(bb.size.Z)],
        "part_count": len(parts),
        "params": asdict(p),
    }
    (out / "module1_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return module, parts, info


def main():
    p = Params()
    module, parts, info = build(p)
    print("검사 통과: 부품 간섭 없음, X·Y 방향 결합 시 간섭 없음, 핀-구멍 위치 일치")
    for r in write_bom(parts):
        print(" | ".join(str(x) for x in r))
    print(f"외형 {info['outer_size_mm']} mm, 무게 {info['mass_g']} g, 무게중심 {info['center_of_mass_mm']}")


if __name__ == "__main__":
    sys.exit(main())
