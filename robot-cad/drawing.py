"""치수가 들어간 도면 생성 (A3, 3각법, 척도 1:1).

실행:  python robot-cad/drawing.py
결과:  out/M1-001_body_drawing.svg / .dxf   본체 제작 도면
       out/M1-000_assembly_drawing.svg      조립도 + 부품표
       (PDF 는 make_pdf.js 가 SVG 를 인쇄해서 만든다)

치수 값은 모두 Params 에서 계산하므로, 숫자를 바꾸고 다시 실행하면 도면도 따라 바뀐다.
"""

from datetime import date
from html import escape
from pathlib import Path

import ezdxf
from build123d import Align, Box, Compound, Pos, Vector

import module1 as m

OUT = m.OUT
SHEET_W, SHEET_H = 420, 297          # A3 가로
FONT = "'NanumGothic','Noto Sans KR','Malgun Gothic','WenQuanYi Zen Hei',sans-serif"

# 보는 방향별: (카메라 방향, 위쪽, 가로축 벡터, 세로축 벡터)
VIEWS = {
    "front": ((0, -1, 0), (0, 0, 1), Vector(1, 0, 0), Vector(0, 0, 1)),
    "top":   ((0, 0, 1),  (0, 1, 0), Vector(1, 0, 0), Vector(0, 1, 0)),
    "right": ((1, 0, 0),  (0, 0, 1), Vector(0, 1, 0), Vector(0, 0, 1)),
    "iso":   ((0.6, -0.6, 0.5), (0, 0, 1), None, None),
}


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def polyline(edge):
    """모서리 하나를 점 목록으로 (직선은 2점, 곡선은 잘게 나눔)."""
    n = 1 if edge.geom_type.name == "LINE" else 24
    return [tuple(edge @ (i / n))[:2] for i in range(n + 1)]


class Sheet:
    """도면 한 장. 좌표는 mm, 원점은 왼쪽 위, Y 는 아래로 증가."""

    def __init__(self, title, number, material, scale="1:1"):
        self.svg = []
        self.title, self.number, self.material, self.scale = title, number, material, scale
        self.doc = ezdxf.new("R2010", setup=True)
        self.doc.units = ezdxf.units.MM
        for name, color, ltype in (("VISIBLE", 7, "CONTINUOUS"), ("HIDDEN", 8, "DASHED"),
                                   ("DIM", 1, "CONTINUOUS"), ("TEXT", 3, "CONTINUOUS"),
                                   ("FRAME", 7, "CONTINUOUS")):
            self.doc.layers.add(name, color=color, linetype=ltype)
        self.msp = self.doc.modelspace()
        self.views = {}

    # DXF 는 Y 가 위로 증가하므로 뒤집어서 기록한다
    def _d(self, x, y):
        return (x, SHEET_H - y)

    def add_view(self, name, shape, center, at, scale=1.0, hidden=True):
        """형상을 투영해 (at) 위치에 그린다. center 는 투영 기준점(모델 좌표)."""
        direction, up, hx, vy = VIEWS[name]
        origin = center + Vector(direction) * 1000
        visible, hid = shape.project_to_viewport(origin, viewport_up=up, look_at=center)
        self.views[name] = (center, at, scale, hx, vy)
        for edges, layer, style in ((hid if hidden else [], "HIDDEN",
                                     'stroke="#666" stroke-width="0.18" stroke-dasharray="1.5 1"'),
                                    (visible, "VISIBLE", 'stroke="#000" stroke-width="0.35"')):
            paths = []
            for e in edges:
                pts = [(at[0] + x * scale, at[1] - y * scale) for x, y in polyline(e)]
                paths.append("M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts))
                self.msp.add_lwpolyline([self._d(x, y) for x, y in pts], dxfattribs={"layer": layer})
            if paths:
                self.svg.append(f'<path d="{" ".join(paths)}" fill="none" {style}/>')

    def pt(self, view, model_point):
        """모델 좌표의 점이 도면에서 어디에 찍히는지."""
        center, at, scale, hx, vy = self.views[view]
        d = Vector(model_point) - center
        return (at[0] + d.dot(hx) * scale, at[1] - d.dot(vy) * scale)

    def text(self, x, y, s, size=3.2, anchor="start", bold=False, layer="TEXT"):
        weight = ' font-weight="700"' if bold else ""
        self.svg.append(f'<text x="{fmt(x)}" y="{fmt(y)}" font-size="{size}" text-anchor="{anchor}"{weight}>{escape(s)}</text>')
        align = {"start": ezdxf.enums.TextEntityAlignment.LEFT, "middle": ezdxf.enums.TextEntityAlignment.CENTER,
                 "end": ezdxf.enums.TextEntityAlignment.RIGHT}[anchor]
        self.msp.add_text(s, height=size * 0.75, dxfattribs={"layer": layer}).set_placement(self._d(x, y), align=align)

    def line(self, x1, y1, x2, y2, layer="DIM", width=0.18, arrows=""):
        marker = {"both": ' marker-start="url(#arr)" marker-end="url(#arr)"', "end": ' marker-end="url(#arr)"'}.get(arrows, "")
        color = "#000" if layer == "FRAME" else "#0a4"
        self.svg.append(f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" stroke="{color}" stroke-width="{width}"{marker}/>')
        if layer == "FRAME":
            self.msp.add_line(self._d(x1, y1), self._d(x2, y2), dxfattribs={"layer": layer})

    def dim_h(self, view, a, b, y, label=None):
        """가로 치수: 모델 점 a, b 사이. y 는 치수선의 도면 Y 좌표."""
        (x1, y1), (x2, y2) = self.pt(view, a), self.pt(view, b)
        value = abs(x2 - x1) / self.views[view][2]
        s = label or fmt(value)
        for x, y0 in ((x1, y1), (x2, y2)):
            self.line(x, y0 + (1 if y > y0 else -1), x, y + (1.5 if y > y0 else -1.5))
        self.line(x1, y, x2, y, arrows="both")
        self.text((x1 + x2) / 2, y - 1, s, anchor="middle", layer="DIM")
        self.msp.add_linear_dim(base=self._d(0, y), p1=self._d(x1, y1), p2=self._d(x2, y2), text=s,
                                dimstyle="EZDXF", override={"dimtxt": 2.5, "dimasz": 2, "dimexe": 1.5, "dimexo": 1},
                                dxfattribs={"layer": "DIM"}).render()

    def dim_v(self, view, a, b, x, label=None):
        """세로 치수: 모델 점 a, b 사이. x 는 치수선의 도면 X 좌표."""
        (x1, y1), (x2, y2) = self.pt(view, a), self.pt(view, b)
        value = abs(y2 - y1) / self.views[view][2]
        s = label or fmt(value)
        for x0, yy in ((x1, y1), (x2, y2)):
            self.line(x0 + (1 if x > x0 else -1), yy, x + (1.5 if x > x0 else -1.5), yy)
        self.line(x, y1, x, y2, arrows="both")
        ym = (y1 + y2) / 2
        self.svg.append(f'<text x="{fmt(x - 1)}" y="{fmt(ym)}" font-size="3.2" text-anchor="middle" '
                        f'transform="rotate(-90 {fmt(x - 1)} {fmt(ym)})">{escape(s)}</text>')
        self.msp.add_linear_dim(base=self._d(x, 0), p1=self._d(x1, y1), p2=self._d(x2, y2), angle=90, text=s,
                                dimstyle="EZDXF", override={"dimtxt": 2.5, "dimasz": 2, "dimexe": 1.5, "dimexo": 1},
                                dxfattribs={"layer": "DIM"}).render()

    def mark(self, view, model_point, letter, dx=5, dy=-5):
        """형상 옆에 기호(A, B, ...)를 붙이고 짧은 지시선을 긋는다."""
        x, y = self.pt(view, model_point)
        self.line(x, y, x + dx, y + dy)
        self.svg.append(f'<circle cx="{fmt(x + dx * 1.35)}" cy="{fmt(y + dy * 1.35)}" r="2.4" fill="#fff" stroke="#0a4" stroke-width="0.18"/>')
        self.text(x + dx * 1.35, y + dy * 1.35 + 1.1, letter, size=3, anchor="middle", bold=True)

    def table(self, x, y, widths, rows, row_h=5.5, size=2.8):
        total = sum(widths)
        for i in range(len(rows) + 1):
            self.line(x, y + i * row_h, x + total, y + i * row_h, layer="FRAME", width=0.25 if i in (0, 1, len(rows)) else 0.12)
        cx = x
        for w in list(widths) + [0]:
            self.line(cx, y, cx, y + len(rows) * row_h, layer="FRAME", width=0.25 if cx in (x, x + total) else 0.12)
            cx += w
        for r, row in enumerate(rows):
            cx = x
            for w, cell in zip(widths, row):
                self.text(cx + 1.2, y + r * row_h + row_h * 0.7, str(cell), size=size, bold=(r == 0))
                cx += w

    def frame(self):
        self.svg.append(f'<rect x="10" y="10" width="{SHEET_W - 20}" height="{SHEET_H - 20}" fill="none" stroke="#000" stroke-width="0.5"/>')
        self.msp.add_lwpolyline([self._d(10, 10), self._d(SHEET_W - 10, 10), self._d(SHEET_W - 10, SHEET_H - 10),
                                 self._d(10, SHEET_H - 10)], close=True, dxfattribs={"layer": "FRAME"})
        x, y = SHEET_W - 10 - 150, SHEET_H - 10 - 28
        self.table(x, y, (22, 53, 22, 53), [
            ("품명", self.title, "도번", self.number),
            ("재질", self.material, "척도", f"{self.scale} (A3)"),
            ("투상", "3각법", "단위", "mm"),
            ("일반공차", "±0.2 (별도 표기 제외)", "작성일", date.today().isoformat()),
            ("비고", "3D 파일(STEP)이 기준", "상태", "개념 설계 (검토용)"),
        ], row_h=5.6)

    def write(self, stem):
        body = "\n".join(self.svg)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W}mm" height="{SHEET_H}mm" '
               f'viewBox="0 0 {SHEET_W} {SHEET_H}" font-family="{FONT}">\n'
               '<defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="3.2" markerHeight="3.2" '
               'orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0 3.4L10 5L0 6.6z" fill="#0a4"/></marker></defs>\n'
               f'<rect width="{SHEET_W}" height="{SHEET_H}" fill="#fff"/>\n{body}\n</svg>\n')
        (OUT / f"{stem}.svg").write_text(svg, encoding="utf-8")
        self.doc.saveas(OUT / f"{stem}.dxf")


def body_drawing(p):
    body = m.make_body(p)
    L, W, H = p.length, p.width, p.height
    c = Vector(0, 0, H / 2)
    sh = Sheet("모듈 1호 본체", "M1-001", "ABS 수지 (3D 프린팅 또는 절삭)")
    front_at, top_at, right_at = (112, 200), (112, 88), (292, 200)
    sh.add_view("top", body, c, top_at)
    sh.add_view("front", body, c, front_at)
    sh.add_view("right", body, c, right_at)
    sh.add_view("iso", body, c, (328, 62), scale=0.45, hidden=False)
    sh.text(top_at[0] - L / 2 - 30, top_at[1] - W / 2 - 3, "평면도", size=3.6, bold=True)
    sh.text(front_at[0] - L / 2 - 30, front_at[1] + H / 2 + 34, "정면도", size=3.6, bold=True)
    sh.text(right_at[0] - W / 2 - 14, right_at[1] + H / 2 + 34, "우측면도", size=3.6, bold=True)
    sh.text(250, 22, "입체도 (참고)", size=3.6, bold=True)

    yb = front_at[1] + H / 2          # 정면도 아랫변의 도면 Y
    # 정면도: 전체 길이, 핀 포함 길이, 높이
    sh.dim_h("front", (-p.contact_dx, 0, H / 2 - p.contact_dz), (p.contact_dx, 0, H / 2 - p.contact_dz), yb + 7)
    sh.dim_h("front", (-L / 2, 0, 0), (L / 2, 0, 0), yb + 14)
    sh.dim_h("front", (-L / 2 - p.pin_h, 0, H / 2 - p.pin_dz), (L / 2 + p.pin_h, 0, H / 2 - p.pin_dz), yb + 21)
    xl = front_at[0] - L / 2
    sh.dim_v("front", (-L / 2, 0, 0), (-L / 2, 0, H), xl - 14)
    # 정면도: 결합부 위치 (면 중심 기준 대칭)
    yt = front_at[1] - H / 2
    sh.dim_h("front", (-p.pin_dx, 0, H / 2 + p.pin_dz), (p.pin_dx, 0, H / 2 + p.pin_dz), yt - 5)
    xr = front_at[0] + L / 2
    sh.dim_v("front", (p.pin_dx, 0, H / 2 - p.pin_dz), (p.pin_dx, 0, H / 2 + p.pin_dz), xr + 14)
    sh.dim_v("front", (p.contact_dx, 0, H / 2 - p.contact_dz), (p.contact_dx, 0, H / 2 + p.contact_dz), xr + 21)
    sh.dim_v("front", (p.pin_dx, 0, 0), (p.pin_dx, 0, H / 2), xr + 28)
    # 정면도: 형상 기호
    sh.mark("front", (-p.pin_dx, 0, H / 2 + p.pin_dz), "A", dx=-5, dy=-4)
    sh.mark("front", (p.pin_dx, 0, H / 2 + p.pin_dz), "B", dx=5, dy=-4)
    sh.mark("front", (0, 0, H / 2), "C", dx=0, dy=7)
    sh.mark("front", (-p.contact_dx, 0, H / 2 + p.contact_dz), "D", dx=-5, dy=2)
    sh.mark("front", (p.contact_dx, 0, H / 2 + p.contact_dz), "E", dx=5, dy=2)
    sh.mark("front", (-p.latch_dx, 0, H / 2 + p.latch_dy), "H", dx=-5, dy=-4)
    sh.mark("front", (p.latch_dx, 0, H / 2 + p.latch_dy), "I", dx=6, dy=5)

    # 평면도: 폭, 내부 공간, 바퀴 축 간격
    cx, cy = m.cavity_size(p)
    xtl = top_at[0] - L / 2
    sh.dim_v("top", (-L / 2, -W / 2, 0), (-L / 2, W / 2, 0), xtl - 14)
    sh.dim_h("top", (-cx / 2, 0, 0), (cx / 2, 0, 0), top_at[1] + 4)
    sh.dim_v("top", (0, -cy / 2, 0), (0, cy / 2, 0), top_at[0] - 8)
    sh.dim_h("top", (-p.wheel_x, W / 2, 0), (p.wheel_x, W / 2, 0), top_at[1] - W / 2 - 9, label=f"{fmt(2 * p.wheel_x)} (바퀴 축 간격)")
    wy = m.wheel_centers(p)[0].Y
    xtr = top_at[0] + L / 2
    sh.dim_v("top", (L / 2, wy - m.well_width(p) / 2, 0), (L / 2, wy + m.well_width(p) / 2, 0), xtr + 14)
    sh.mark("top", (p.wheel_x, wy, 0), "F", dx=6, dy=-3)
    sx, sy = m.standoff_xy(p)[0]
    sh.mark("top", (sx, sy, 0), "G", dx=-4, dy=5)

    # 우측면도: 바퀴 축 높이, 바닥 두께, 덮개 제외 높이
    wz = m.wheel_centers(p)[0].Z
    xrl = right_at[0] - W / 2
    sh.dim_v("right", (0, -W / 2, 0), (0, -W / 2, wz), xrl - 12)
    sh.dim_h("right", (0, -W / 2, 0), (0, W / 2, 0), right_at[1] + H / 2 + 14)
    sh.dim_h("right", (0, -wy, 0), (0, wy, 0), right_at[1] + H / 2 + 21, label=f"{fmt(2 * wy)} (바퀴 중심 간격)")

    notes = [
        ("기호", "내용"),
        ("A", f"결합 핀 뿌리 Ø{fmt(2 * p.pin_r)} → 끝 Ø{fmt(2 * p.pin_tip_r)}, 길이 {fmt(p.pin_h)}. 면마다 2곳, 4면 동일"),
        ("B", f"결합 구멍 Ø{fmt(2 * (p.pin_r + p.pin_clear))}, 깊이 {fmt(p.pin_h + 1)}. 면마다 2곳"),
        ("C", f"자석 자리 Ø{fmt(2 * p.magnet_r)}, 깊이 {fmt(p.magnet_d)}. 면마다 1곳"),
        ("D", f"스프링 핀 구멍 Ø{fmt(2 * p.pogo_r)}, 깊이 {fmt(p.pogo_len - p.pogo_out)}. 면마다 2곳"),
        ("E", f"접촉판 자리 Ø{fmt(2 * (p.pad_r + 0.1))}, 깊이 {fmt(p.pad_recess)}. 면마다 2곳"),
        ("F", f"바퀴집 Ø{fmt(2 * (p.wheel_r + p.well_gap))} x 폭 {fmt(m.well_width(p))}, 축 구멍 Ø{fmt(2 * (p.shaft_r + 0.3))}. 4곳"),
        ("G", f"기판 받침 기둥 Ø{fmt(2 * p.standoff_r)}, 윗면 높이 {fmt(p.pcb_z)}. 4곳"),
        ("H", f"잠금 볼트 축 구멍 Ø{fmt(2 * (p.latch_shaft_r + 0.2))} 관통. 면 중심에서 왼쪽 {fmt(p.latch_dx)}, 위 {fmt(p.latch_dy)}. 면마다 1곳"),
        ("I", f"잠금 홈 {fmt(p.latch_head_w + 0.8)} x {fmt(p.latch_head_len + 1)} 깊이 {fmt(p.latch_wall)}, 그 뒤 Ø{fmt(p.latch_head_len + 1.6)} 깊이 {fmt(m.latch_pocket_depth(p))}. 면 중심에서 오른쪽 {fmt(p.latch_dx)}, 위 {fmt(p.latch_dy)}"),
        ("-", f"바퀴 축 높이: 바닥면에서 {fmt(wz)} (우측면도)"),
        ("-", f"바닥 두께 {fmt(p.floor_t)}, 세로 모서리 R{fmt(p.corner_r)}, 내부 공간은 위로 열림"),
    ]
    sh.table(248, 108, (10, 150), notes, row_h=4.6, size=2.6)
    sh.frame()
    sh.write("M1-001_body_drawing")


def assembly_drawing(p):
    parts = m.make_parts(p)
    inside = Compound(children=[s for k, s in parts if k != "lid"])
    c = Vector(0, 0, p.height / 2)
    sh = Sheet("모듈 1호 조립도", "M1-000", "부품표 참조")
    sh.add_view("top", inside, c, (102, 98), hidden=False)
    sh.add_view("front", Compound(children=[s for _, s in m.make_parts(p)]), c, (102, 218))
    sh.text(16, 20, "평면도 (덮개 제거)", size=3.6, bold=True)
    sh.text(16, 280, "정면도", size=3.6, bold=True)
    # 부품 지시
    _, cy = m.cavity_size(p)
    w0 = m.wheel_centers(p)[0]
    sh.mark("top", (w0.X, cy / 2 - p.motor_len / 2, 0), "101", dx=-3, dy=-22)
    sh.mark("top", (0, 0, 0), "103", dx=6, dy=-6)
    sh.mark("top", (p.cell_len / 2 - 4, -p.cell_dy, 0), "102", dx=22, dy=40)
    sh.mark("top", (p.length / 2, 0, 0), "104", dx=7, dy=4)
    wall = m.face_walls(p)[0]
    sh.mark("top", (p.length / 2 + p.latch_wall + 2, -p.latch_dx, 0), "107", dx=8, dy=-3)
    sh.mark("top", (p.length / 2 - wall - p.servo_gap - 8, -p.latch_dx + 10, 0), "108", dx=22, dy=6)
    sh.mark("front", (w0.X, 0, w0.Z - p.wheel_r + 2), "003", dx=6, dy=5)
    sh.mark("front", (0, 0, p.height + p.lid_t / 2), "002", dx=5, dy=-5)
    sh.mark("front", (-p.length / 2 + 6, 0, p.height / 2 + 4), "001", dx=-9, dy=-6)
    mass, cog = m.mass_summary(parts)
    bb = Compound(children=[s for _, s in m.make_parts(p)]).bounding_box()
    sh.dim_h("front", (bb.min.X, 0, 0), (bb.max.X, 0, 0), 218 + p.height / 2 + 18)
    sh.dim_v("front", (-p.length / 2, 0, bb.min.Z), (-p.length / 2, 0, bb.max.Z), 102 - p.length / 2 - 18)

    rows = [(r[0][-3:] if r[0] else "", r[0], r[1], r[2], r[4], r[7]) for r in m.bom_rows(parts)]
    rows[0] = ("기호", "품번", "품명", "수량", "무게(g)", "비고")
    sh.text(190, 24, "부품표", size=4, bold=True)
    sh.table(190, 28, (12, 20, 42, 12, 16, 108), rows, row_h=6)
    y = 28 + 6 * len(rows) + 12
    for i, line in enumerate([
        f"총 무게 약 {mass:.0f} g (배선·나사 제외), 무게중심 높이 바닥면에서 {cog.Z:.0f} mm",
        f"외형 {bb.size.X:.0f} x {bb.size.Y:.0f} x {bb.size.Z:.0f} mm (결합 핀·바퀴 포함)",
        "결합부: 암수 구분 없음. 밖에서 볼 때 왼쪽 핀·오른쪽 구멍, 윗줄 접점 +, 아랫줄 접점 -. 잠금장치는 도면 M1-107 참조",
        "102 배터리는 기판(103) 아래에 있다. 구매 부품(101~108)은 규격품 대표 치수로 자리만 잡은 것이며 제품 선정 후 수정한다.",
        "단가는 소량 구매 기준 추정값이다. 부품표 CSV 참조.",
    ]):
        sh.text(190, y + i * 6.5, "· " + line, size=3)
    sh.frame()
    sh.write("M1-000_assembly_drawing")


def latch_drawing(p):
    """잠금장치 도면: 잠금 볼트 부품도 + 풀림·잠금 상태 단면 + 강도 요약."""
    import joint_loads

    L, H = p.length, p.height
    wall = m.face_walls(p)[0]
    loc = m.side_planes(p)[0].location              # +X 면
    zc = H / 2 + p.latch_dy                          # 볼트 축 높이
    yc = -p.latch_dx                                 # +X 면에서 볼트의 세계 좌표 Y
    body_a = m.make_body(p)
    body_b = Pos(L, 0, 0) * m.make_body(p)
    servo = loc * m.make_latch_servo(p, wall)
    # 볼트 축 높이에서 자른 아래쪽 절반만, 잠금장치 둘레만 남긴다
    rx0, rx1 = L / 2 - wall - p.servo_gap - 12, L / 2 + 13       # 서보 앞부분부터 상대 모듈 안쪽까지
    ry0, ry1 = yc - 8, yc + p.servo_l - p.servo_offset + 3
    region = Pos((rx0 + rx1) / 2, (ry0 + ry1) / 2, zc) * Box(rx1 - rx0, ry1 - ry0, 14, align=(Align.CENTER, Align.CENTER, Align.MAX))
    sh = Sheet("결합부 잠금장치", "M1-107", "볼트: 강재 / 본체: ABS 수지", scale="표기")
    centre = Vector((rx0 + rx1) / 2, (ry0 + ry1) / 2, zc - 7)
    half_h = (ry1 - ry0) / 2 * 3
    for row, (locked, label) in enumerate(((False, "풀림: 머리가 세로 (홈과 같은 방향) → 빠진다"),
                                           (True, "잠금: 머리를 90° 돌림 → 벽 뒤에 걸린다"))):
        bolt = loc * m.make_latch_bolt(p, wall, locked)
        pieces = []
        for shape in (body_a, body_b, bolt, servo):
            found = shape.intersect(region)
            if found:
                pieces += list(found) if isinstance(found, (list, tuple)) else [found]
        cut = Compound(children=pieces)
        at = (112, 82 + row * 118)
        sh.add_view("top", cut, centre, at, scale=3, hidden=False)
        sh.text(20, at[1] - half_h - 5, f"단면 {'A' if row == 0 else 'B'} (척도 3:1, 볼트 축 높이에서 자른 평면)  {label}", size=3.4, bold=True)
        x_face = at[0] + (L / 2 - centre.X) * 3
        sh.text(x_face - 3, at[1] + half_h + 6, "← 모듈 1", size=3, anchor="end")
        sh.text(x_face + 3, at[1] + half_h + 6, "모듈 2 →", size=3)
        sh.mark("top", (L / 2 + p.latch_wall + p.latch_clear + 1.5, yc, zc), "1", dx=4, dy=-9)
        sh.mark("top", (L / 2 - wall - p.servo_gap - 10, yc + 6, zc), "2", dx=-3, dy=-9)
        sh.mark("top", (L / 2 - wall - 1, yc - 3, zc), "3", dx=-2, dy=9)
        if row == 1:
            sh.dim_h("top", (L / 2, ry0, zc), (L / 2 + p.latch_wall, ry0, zc), at[1] + half_h + 15, label=f"벽 {fmt(p.latch_wall)}")
            sh.dim_h("top", (L / 2 - wall, ry0, zc), (L / 2, ry0, zc), at[1] + half_h + 22, label=f"벽 {fmt(wall)}")

    # 잠금 볼트 부품도 (척도 4:1): 옆에서 본 모습과 머리 쪽에서 본 모습
    bolt = m.make_latch_bolt(p, wall, locked=True)      # 면 기준 좌표: 축이 Z 방향
    bc = Vector(-p.latch_dx, p.latch_dy, 0)
    sh.text(232, 22, "잠금 볼트 M1-107 (척도 4:1)", size=3.4, bold=True)
    sh.add_view("front", bolt, bc + Vector(0, 0, -6), (268, 88), scale=4, hidden=False)   # 가로 = 머리 길이, 세로 = 축
    sh.add_view("top", bolt, bc, (352, 88), scale=4, hidden=False)
    z0 = p.latch_wall + p.latch_clear
    top, bottom = z0 + p.latch_head_t, -(wall + p.servo_gap)
    hx = -p.latch_dx
    sh.dim_h("front", (hx - p.latch_head_len / 2, 0, top), (hx + p.latch_head_len / 2, 0, top), 88 - (top + 6) * 4 - 6)
    sh.dim_v("front", (hx + p.latch_head_len / 2, 0, z0), (hx + p.latch_head_len / 2, 0, top), 268 + p.latch_head_len * 2 + 8)
    sh.dim_v("front", (hx - p.latch_head_len / 2, 0, bottom), (hx - p.latch_head_len / 2, 0, top), 268 - p.latch_head_len * 2 - 10)
    sh.dim_h("front", (hx - p.latch_shaft_r, 0, bottom), (hx + p.latch_shaft_r, 0, bottom), 88 - (bottom + 6) * 4 + 7, label=f"Ø{fmt(2 * p.latch_shaft_r)}")
    sh.dim_h("front", (hx - p.latch_collar_r, 0, -wall), (hx + p.latch_collar_r, 0, -wall), 88 - (bottom + 6) * 4 + 14, label=f"턱 Ø{fmt(2 * p.latch_collar_r)}")
    sh.dim_v("top", (hx + p.latch_head_len / 2, p.latch_dy - p.latch_head_w / 2, 0),
             (hx + p.latch_head_len / 2, p.latch_dy + p.latch_head_w / 2, 0), 352 + p.latch_head_len * 2 + 8)
    sh.text(352, 122, "머리 쪽에서 본 모습", size=2.8, anchor="middle")
    sh.text(232, 160, f"턱 두께 {fmt(p.latch_collar_t)}, 머리 아랫면에서 턱 윗면까지 {fmt(z0 + wall - p.latch_collar_t)} (X 면 기준)", size=2.8)

    sh.table(232, 165, (10, 168), [
        ("기호", "내용"),
        ("1", "잠금 볼트. 강재. T형 머리가 상대 모듈의 세로 홈으로 들어간 뒤 90° 돌아 벽 뒤에 걸린다"),
        ("2", "소형 서보모터(9g 급). 볼트를 90° 돌린다. 걸린 뒤에는 모터 힘 없이 형상으로 버틴다"),
        ("3", "턱. 볼트가 당겨질 때 자기 모듈의 안쪽 벽에 걸려 힘을 본체로 전달한다"),
        ("-", "면마다 왼쪽에 볼트, 오른쪽에 홈이 있어 붙은 면에서는 볼트 2개가 서로의 홈에 걸린다"),
        ("-", "한쪽 모듈이 고장 나도 다른 쪽 볼트 1개로 붙어 있을 수 있다"),
    ], row_h=4.4, size=2.6)

    calc = joint_loads.compute(p)
    rows = [("상황", "필요한 힘", "안전율 (볼트 1개)", "안전율 (볼트 2개)")]
    for c in calc["cases"]:
        rows.append((c["name"], f"{c['required_N']:.0f} N", f"{c['sf_single']:.1f}", f"{c['sf_double']:.1f}"))
    sh.text(232, 200, f"강도 요약: 볼트 1개의 허용 힘 약 {calc['capacity_N']:.0f} N ({calc['limit']} 기준, 가정값)", size=3, bold=True)
    sh.table(232, 203, (82, 28, 34, 34), rows, row_h=4.3, size=2.6)
    sh.text(232, 203 + 4.3 * len(rows) + 5, "허용 응력은 가정값이다. 3D 프린팅 부품은 실제 시험으로 확인해야 한다.", size=2.6)
    sh.frame()
    sh.write("M1-107_latch_drawing")


def main():
    p = m.Params()
    OUT.mkdir(exist_ok=True)
    body_drawing(p)
    assembly_drawing(p)
    latch_drawing(p)
    print("도면 생성 완료: M1-001_body_drawing, M1-000_assembly_drawing, M1-107_latch_drawing (SVG, DXF)")


if __name__ == "__main__":
    main()
