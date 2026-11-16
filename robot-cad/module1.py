"""모듈 1호 설계 (본체 + 결합부 + 구동부 + 전원 + 기판).

실행:  python robot-cad/module1.py
결과:  robot-cad/out/ 폴더에 STEP·GLB(3D), SVG·DXF(도면), CSV(부품표) 생성

치수는 모두 mm. 아래 Params 의 숫자만 바꾸면 형상 전체가 따라 바뀐다.
구매 부품(모터·배터리·기판)은 시중 규격품의 대표 치수로 자리만 잡은 것이다.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
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
    # 잠금장치 (T형 볼트를 90도 돌려 상대 면의 홈 뒤에 건다. 왼쪽 볼트, 오른쪽 홈)
    latch_dx: float = 30         # 면 중심에서 좌우 거리
    latch_dy: float = 16         # 면 중심에서 위로
    latch_shaft_r: float = 2     # 볼트 축 반지름
    latch_head_len: float = 12   # T형 머리 길이
    latch_head_w: float = 4      # T형 머리 폭
    latch_head_t: float = 3      # T형 머리 두께
    latch_wall: float = 3        # 머리가 걸리는 벽 두께 (홈 앞쪽 벽)
    latch_clear: float = 0.2     # 머리와 벽 사이 틈
    latch_collar_r: float = 4    # 볼트가 빠지지 않게 안쪽 벽에 걸리는 턱
    latch_collar_t: float = 2
    # 잠금용 서보모터 (9g 급 대표 치수)
    servo_l: float = 23          # 긴 변
    servo_t: float = 12.5        # 두께
    servo_d: float = 26          # 축 방향 깊이
    servo_offset: float = 6      # 긴 변 끝에서 출력축까지
    servo_gap: float = 3         # 안쪽 벽에서 서보 앞면까지
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
    pcb_z: float = 30        # 기판 아랫면 높이 (위쪽은 잠금용 서보 자리)
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


def face_walls(p):
    """옆면 4곳(side_planes 와 같은 순서)의 벽 두께: 면에서 내부 공간까지."""
    cx, cy = cavity_size(p)
    tx, ty = (p.length - cx) / 2, (p.width - cy) / 2
    return [tx, tx, ty, ty]


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
    # 잠금장치: 왼쪽은 볼트 축 구멍(내부 공간까지 관통), 오른쪽은 세로 홈 + 머리가 도는 자리
    cut.append(Pos(-p.latch_dx, p.latch_dy, 0) * Cylinder(p.latch_shaft_r + 0.2, max(p.length, p.width) / 3, align=TOP))
    cut.append(Pos(p.latch_dx, p.latch_dy, 0) * Box(p.latch_head_w + 0.8, p.latch_head_len + 1.0, p.latch_wall, align=TOP))
    cut.append(Pos(p.latch_dx, p.latch_dy, -p.latch_wall) *
               Cylinder(p.latch_head_len / 2 + 0.8, latch_pocket_depth(p), align=TOP))
    return add, cut


def latch_pocket_depth(p):
    return p.latch_head_t + 2 * p.latch_clear + 0.4


def make_latch_bolt(p, wall, locked):
    """잠금 볼트 (면 기준 좌표). locked=False 면 머리가 세로(홈과 같은 방향)라 빠진다."""
    z0 = p.latch_wall + p.latch_clear                   # 머리 아랫면: 상대 벽 바로 뒤
    head = Pos(0, 0, z0) * Box(p.latch_head_len, p.latch_head_w, p.latch_head_t, align=BOTTOM)
    if not locked:
        head = Rot(0, 0, 90) * head
    back = wall + p.servo_gap                           # 축은 서보 앞면까지
    shaft = Pos(0, 0, z0 + p.latch_head_t) * Cylinder(p.latch_shaft_r, z0 + p.latch_head_t + back, align=TOP)
    collar = Pos(0, 0, -wall) * Cylinder(p.latch_collar_r, p.latch_collar_t, align=TOP)
    return Pos(-p.latch_dx, p.latch_dy, 0) * (head + shaft + collar)


def make_latch_servo(p, wall):
    """잠금 볼트를 돌리는 서보 (면 기준 좌표). 몸통은 면 중심 쪽으로 뻗는다."""
    x0 = -p.latch_dx - p.servo_offset
    box = Box(p.servo_l, p.servo_t, p.servo_d, align=(Align.MIN, Align.CENTER, Align.MAX))
    return Pos(x0, p.latch_dy, -(wall + p.servo_gap)) * box


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


def make_face_parts(p, locked=False):
    """옆면마다 들어가는 자석·스프링 핀·접촉판·잠금 볼트·서보."""
    magnets, pogos, pads, latches, servos = [], [], [], [], []
    for plane, wall in zip(side_planes(p), face_walls(p)):
        loc = plane.location
        latches.append(loc * make_latch_bolt(p, wall, locked))
        servos.append(loc * make_latch_servo(p, wall))
        magnets.append(loc * Cylinder(p.magnet_r - 0.1, p.magnet_d, align=TOP))
        for dz in (p.contact_dz, -p.contact_dz):
            pogos.append(loc * Pos(-p.contact_dx, dz, p.pogo_out) * Cylinder(p.pogo_r, p.pogo_len, align=TOP))
            pads.append(loc * Pos(p.contact_dx, dz, -p.pad_recess) * Cylinder(p.pad_r, p.pad_t, align=BOTTOM))
    return magnets, pogos, pads, latches, servos


# 부품 종류별 정보: 품번, 품명, 색, 무게 계산 방식, 소량 구매 단가(달러, 조사 메모 기준 추정)
# 무게: ("density", g/mm3) 는 부피로 계산, ("each", g) 는 규격품 대표 무게
KINDS = {
    "body":   ("M1-001", "본체",            (0.80, 0.82, 0.85), ("density", 1.05e-3), None,  "ABS 수지, 결합 핀·기판 받침 일체형"),
    "lid":    ("M1-002", "덮개",            (0.25, 0.45, 0.80), ("density", 1.05e-3), None,  "ABS 수지"),
    "wheel":  ("M1-003", "바퀴",            (0.15, 0.15, 0.15), ("density", 1.10e-3), None,  "수지 휠 + 고무 타이어"),
    "motor":  ("M1-101", "기어모터 (N20 급)", (0.75, 0.60, 0.20), ("each", 10.0),       10.0,  "바퀴마다 1개, 연장축 필요"),
    "cell":   ("M1-102", "배터리 셀 18650",  (0.20, 0.65, 0.35), ("each", 46.0),       5.0,   "2개 직렬 7.4V 가정"),
    "pcb":    ("M1-103", "제어 기판",        (0.10, 0.45, 0.25), ("each", 25.0),       15.0,  "ESP32 급 + 모터 드라이버 + 충전 회로"),
    "magnet": ("M1-104", "결합용 자석",      (0.70, 0.70, 0.75), ("density", 7.5e-3),  1.0,   "지름 12 x 3, 붙을 때 위치를 잡는 용도"),
    "pogo":   ("M1-105", "스프링 접점 핀",   (0.85, 0.70, 0.25), ("each", 0.3),        0.4,   "면마다 +, - 각 1개"),
    "pad":    ("M1-106", "접촉판",           (0.85, 0.70, 0.25), ("each", 0.1),        0.1,   "면마다 +, - 각 1개"),
    "latch":  ("M1-107", "잠금 볼트 (T형)",  (0.55, 0.57, 0.62), ("density", 7.85e-3), 1.0,   "강재, 면마다 1개. 90도 돌려 잠금"),
    "servo":  ("M1-108", "소형 서보모터 (9g 급)", (0.20, 0.35, 0.75), ("each", 9.0),   3.0,   "면마다 1개, 잠금 볼트 회전"),
}


def make_parts(p, locked=False):
    """[(종류, 형상)] 목록. locked=True 면 잠금 볼트를 잠근 상태로 만든다."""
    parts = [("body", make_body(p)), ("lid", make_lid(p))]
    for c in wheel_centers(p):
        parts.append(("wheel", make_wheel(p, c)))
        parts.append(("motor", make_motor(p, c)))
    parts += [("cell", make_cell(p, 1)), ("cell", make_cell(p, -1)), ("pcb", make_pcb(p))]
    magnets, pogos, pads, latches, servos = make_face_parts(p, locked)
    parts += [("magnet", m) for m in magnets] + [("pogo", g) for g in pogos] + [("pad", d) for d in pads]
    parts += [("latch", b) for b in latches] + [("servo", v) for v in servos]
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


def check_latch(p):
    """붙인 상태에서 잠금 볼트가 (1) 풀린 방향이면 걸림 없이 빠지고 (2) 잠근 방향이면 빠지지 않는지 확인."""
    body = make_body(p)
    planes, walls = side_planes(p), face_walls(p)
    for idx, shift, name in ((0, Vector(p.length, 0, 0), "X"), (2, Vector(0, p.width, 0), "Y")):
        loc = planes[idx].location
        opened = loc * make_latch_bolt(p, walls[idx], locked=False)
        closed = loc * make_latch_bolt(p, walls[idx], locked=True)
        step = shift.normalized()
        for bolt, state in ((opened, "풀림"), (closed, "잠금")):
            assert _volume(bolt.intersect(body)) < 1e-2, f"{name} 면 잠금 볼트({state})가 자기 본체와 겹침"
            assert _volume(bolt.intersect(Pos(shift) * body)) < 1e-2, f"{name} 면 잠금 볼트({state})가 상대 본체와 겹침"
        for pull in (1, 3, 6):      # 상대를 떼어 내는 방향으로 조금씩 옮겨 본다
            moved = Pos(shift + step * pull) * body
            assert _volume(opened.intersect(moved)) < 1e-2, f"{name} 면: 풀린 상태인데 {pull} mm 에서 걸림"
        held = _volume(closed.intersect(Pos(shift + step * 1.0) * body))
        assert held > 1, f"{name} 면: 잠근 상태인데 상대가 빠짐"
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


def export_glb(shape, path):
    """웹 뷰어용 3D 파일. 화면 표시용이라 곡면을 조금 거칠게 나눠 용량을 줄인다."""
    export_gltf(shape, str(path), binary=True, linear_deflection=0.05, angular_deflection=0.3)


def bom_rows(parts):
    rows = [("품번", "품명", "수량", "개당무게_g", "무게합_g", "개당단가_USD(추정)", "금액_USD(추정)", "비고")]
    seen = {}
    for kind, shape in parts:
        seen.setdefault(kind, []).append(shape)
    total_m = total_c = 0.0
    for kind, shapes in seen.items():
        no, name, _, _, price, note = KINDS[kind]
        qty = len(shapes)
        each = sum(part_mass(kind, x) for x in shapes) / qty      # 면마다 길이가 다른 부품은 평균
        cost = price * qty if price is not None else None
        total_m += each * qty
        total_c += cost or 0
        rows.append((no, name, qty, f"{each:.1f}", f"{each * qty:.0f}",
                     "" if price is None else f"{price:.1f}", "" if cost is None else f"{cost:.1f}", note))
    rows.append(("", "합계", "", "", f"{total_m:.0f}", "", f"{total_c:.1f}", "제작품(본체·덮개·바퀴) 가공비는 미포함"))
    return rows


def bom_items(parts):
    """웹 화면용 부품 목록 (종류 이름 포함)."""
    seen = {}
    for kind, shape in parts:
        seen.setdefault(kind, []).append(shape)
    items = []
    for kind, shapes in seen.items():
        no, name, color, _, price, note = KINDS[kind]
        each = sum(part_mass(kind, x) for x in shapes) / len(shapes)
        items.append({"kind": kind, "no": no, "name": name, "qty": len(shapes), "mass_each_g": round(each, 1),
                      "mass_g": round(each * len(shapes)), "price_usd": price, "note": note,
                      "color": [round(c, 2) for c in color]})
    return items


def write_bom(parts, out=OUT):
    rows = bom_rows(parts)
    with open(out / "module1_bom.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    return rows


def build(p, out=OUT, drawings=True):
    """모듈 한 대를 만들고 검사한 뒤 파일로 내보낸다. 요약 정보를 돌려준다."""
    out.mkdir(parents=True, exist_ok=True)
    parts = make_parts(p)
    check_internal(parts)
    check_docking(p)
    check_latch(p)
    module = make_module(p, parts=parts)
    export_step(module, str(out / "module1.step"))
    export_glb(module, out / "module1.glb")
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
        "bom": bom_items(parts),
    }
    write_bom(parts, out)
    (out / "module1_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return module, parts, info


def main():
    ap = argparse.ArgumentParser(description="모듈 1호 생성")
    ap.add_argument("--params", help='바꿀 치수를 JSON 으로. 예: \'{"length": 140}\'')
    ap.add_argument("--out", help="결과 폴더 (기본: robot-cad/out)")
    ap.add_argument("--no-drawings", action="store_true", help="형상 확인용 도면 생략 (빠름)")
    args = ap.parse_args()

    values = asdict(Params())
    if args.params:
        for key, value in json.loads(args.params).items():
            if key not in values:
                raise SystemExit(f"알 수 없는 치수 이름: {key}")
            values[key] = float(value)
    p = Params(**values)
    out = Path(args.out) if args.out else OUT
    try:
        module, parts, info = build(p, out=out, drawings=not args.no_drawings and out == OUT)
    except AssertionError as e:
        raise SystemExit(f"설계 검사 실패: {e}")
    print("검사 통과: 부품 간섭 없음, X·Y 방향 결합 시 간섭 없음, 핀-구멍 위치 일치, 잠금 볼트 풀림·잠금 동작 확인")
    for r in bom_rows(parts):
        print(" | ".join(str(x) for x in r))
    print(f"외형 {info['outer_size_mm']} mm, 무게 {info['mass_g']} g, 무게중심 {info['center_of_mass_mm']}")


if __name__ == "__main__":
    sys.exit(main())
