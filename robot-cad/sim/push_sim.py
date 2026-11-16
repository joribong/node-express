"""합체 효과 시뮬레이션: 같은 짐을 1대와 4대(2 x 2)가 각각 밀어 본다.

실행:  MUJOCO_GL=egl python robot-cad/sim/push_sim.py
결과:  out/sim_push.mp4, out/sim_push.gif, out/sim_push_frame.png, out/sim_results.json

물리 엔진은 MuJoCo. 모듈 치수와 무게는 설계(module1.py)에서 가져온다.
바퀴·짐의 마찰계수와 모터 힘은 가정값이며 파일 위쪽에서 바꿀 수 있다.
결합부는 완전히 단단하다고 보고, 그 자리에 걸리는 힘만 측정한다.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont
import mujoco
import numpy as np

import module1 as m

OUT = m.OUT
try:
    FONT_KR = ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 28)
except OSError:
    FONT_KR = ImageFont.load_default()
MU_WHEEL = 0.8        # 고무 바퀴와 바닥 (가정)
MU_LOAD = 0.5         # 짐과 바닥 (가정)
MU_FACE = 0.1         # 모듈 옆면과 짐 사이 (미끄럽다고 가정: 짐에 기대어 얻는 이득을 빼기 위함)
MOTOR_TORQUE = 0.06   # 모터 하나의 최대 회전력 N·m (가정, 모터 선정 후 수정)
WHEEL_SPEED = 6.0     # 목표 바퀴 회전 속도 rad/s
LOAD_KG = 3.0         # 영상에서 미는 짐의 무게
DURATION = 6.0


def module_xml(p, mass_kg, name, pos, joint="", color="0.25 0.45 0.80"):
    """모듈 한 대의 몸체 정의. 치수 단위는 m."""
    L, W, H = p.length / 1000, p.width / 1000, (p.height + p.lid_t) / 1000
    r, ww = p.wheel_r / 1000, p.wheel_w / 1000
    clear = p.ground_clearance / 1000
    wheel_mass = 0.0125
    chassis_mass = mass_kg - 4 * wheel_mass
    wheels = ""
    for i, c in enumerate(m.wheel_centers(p)):
        wheels += f"""
      <body name="{name}_w{i}" pos="{c.X / 1000} {c.Y / 1000} {r - clear - H / 2}">
        <joint name="{name}_j{i}" type="hinge" axis="0 1 0" damping="0.0005" armature="0.0002"/>
        <geom type="cylinder" size="{r} {ww / 2}" euler="90 0 0" mass="{wheel_mass}"
              friction="{MU_WHEEL} 0.005 0.0001" rgba="0.12 0.12 0.12 1"/>
      </body>"""
    return f"""
    <body name="{name}" pos="{pos[0]} {pos[1]} {pos[2]}">
      {joint}
      <geom name="{name}_g" type="box" size="{L / 2} {W / 2} {H / 2}" mass="{chassis_mass}"
            friction="{MU_FACE} 0.005 0.0001" priority="1" rgba="{color} 1"/>
      <site name="{name}_s" pos="0 0 0" size="0.004"/>{wheels}
      __CHILDREN_{name}__
    </body>"""


def scene_xml(p, mass_kg, lanes):
    """lanes: [(이름, 모듈 격자 칸 목록, 짐 무게 kg, 차선 중심 y)]"""
    L, W = p.length / 1000, p.width / 1000
    H = (p.height + p.lid_t) / 1000
    z0 = H / 2 + p.ground_clearance / 1000
    bodies, actuators, sensors = "", "", ""
    for lane, cells, load_kg, y0 in lanes:
        # 격자 칸을 나무 구조로 연결: 첫 칸이 뿌리, 나머지는 이미 놓인 이웃의 자식
        placed, xml = {}, None
        order = sorted(cells)
        for cx, cy in order:
            name = f"{lane}_m{cx}{cy}"
            color = "0.25 0.45 0.80" if (cx + cy) % 2 == 0 else "0.45 0.65 0.95"
            parent = next(((px, py) for (px, py) in placed if abs(px - cx) + abs(py - cy) == 1), None)
            if parent is None:
                xml = module_xml(p, mass_kg, name, (cx * L, y0 + cy * W, z0), "<freejoint/>", color)
            else:
                pname = placed[parent]
                child = module_xml(p, mass_kg, name, ((cx - parent[0]) * L, (cy - parent[1]) * W, 0), color=color)
                xml = xml.replace(f"__CHILDREN_{pname}__", child + f"__CHILDREN_{pname}__")
                sensors += f'<force name="{name}_f" site="{name}_s"/><torque name="{name}_t" site="{name}_s"/>'
            placed[(cx, cy)] = name
            for i in range(4):
                actuators += (f'<velocity joint="{name}_j{i}" kv="0.02" '
                              f'forcerange="{-MOTOR_TORQUE} {MOTOR_TORQUE}" ctrlrange="-20 20"/>')
        for name in placed.values():
            xml = xml.replace(f"__CHILDREN_{name}__", "")
        bodies += xml
        nx = max(c[0] for c in cells) + 1
        ny = max(c[1] for c in cells) + 1
        lx, ly, lz = 0.20, 0.26, 0.16
        bodies += f"""
    <body name="{lane}_load" pos="{(nx - 0.5) * L + lx / 2 + 0.01} {y0 + (ny - 1) * W / 2} {lz / 2}">
      <freejoint/>
      <geom type="box" size="{lx / 2} {ly / 2} {lz / 2}" mass="{load_kg}"
            friction="{MU_LOAD} 0.005 0.0001" rgba="0.85 0.55 0.20 1"/>
    </body>
    <geom type="box" pos="{(nx - 0.5) * L + lx + 0.01} {y0 + (ny - 1) * W / 2} 0.0005" size="0.003 0.19 0.0005"
          contype="0" conaffinity="0" rgba="0.85 0.1 0.1 1"/>"""
    return f"""
<mujoco>
  <option timestep="0.002" cone="elliptic" impratio="10" integrator="implicitfast"/>
  <visual><global offwidth="1280" offheight="720"/><quality shadowsize="2048"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.35 0.35 0.35" specular="0 0 0"/></visual>
  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.86 0.88 0.90" rgb2="0.78 0.80 0.83" width="256" height="256"/>
    <material name="grid" texture="grid" texrepeat="48 48" reflectance="0"/>
  </asset>
  <worldbody>
    <light pos="0.5 -1 2.5" dir="0 0.3 -1" diffuse="0.45 0.45 0.45" specular="0.1 0.1 0.1"/>
    <geom name="floor" type="plane" size="12 12 0.1" material="grid" friction="{MU_LOAD} 0.005 0.0001"/>
    {bodies}
  </worldbody>
  <actuator>{actuators}</actuator>
  <sensor>{sensors}</sensor>
</mujoco>"""


def caption(frame, t):
    """영상 위에 설명 글자를 얹는다."""
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, img.width, 64), fill=(15, 23, 42))
    draw.text((24, 14), f"같은 짐 {LOAD_KG:g} kg 밀기   |   왼쪽: 4대 합체   오른쪽: 1대 단독   |   빨간 선 = 짐의 출발 위치",
              font=FONT_KR, fill=(255, 255, 255))
    draw.text((img.width - 150, img.height - 44), f"{t:4.1f} 초", font=FONT_KR, fill=(15, 23, 42))
    return np.asarray(img)


def run(p, mass_kg, lanes, duration=DURATION, video=None):
    model = mujoco.MjModel.from_xml_string(scene_xml(p, mass_kg, lanes))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    start = {lane: data.body(f"{lane}_load").xpos.copy() for lane, *_ in lanes}
    renderer, frames = None, []
    if video:
        renderer = mujoco.Renderer(model, 720, 1280)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = (0.45, 0.25, 0.05)
        cam.distance, cam.azimuth, cam.elevation = 1.75, -62, -32
    peak_force = peak_torque = 0.0
    fps, next_frame = 30, 0.0
    while data.time < duration:
        data.ctrl[:] = WHEEL_SPEED if data.time > 0.3 else 0.0
        mujoco.mj_step(model, data)
        if model.nsensor:
            s = data.sensordata.reshape(-1, 3)
            peak_force = max(peak_force, float(np.linalg.norm(s[0::2], axis=1).max()))
            peak_torque = max(peak_torque, float(np.linalg.norm(s[1::2], axis=1).max()))
        if renderer and data.time >= next_frame:
            renderer.update_scene(data, cam)
            frames.append(caption(renderer.render(), data.time))
            next_frame += 1 / fps
    moved = {lane: float(data.body(f"{lane}_load").xpos[0] - start[lane][0]) for lane, *_ in lanes}
    if video:
        imageio.mimsave(OUT / f"{video}.mp4", frames, fps=fps, quality=7, macro_block_size=16)
        imageio.mimsave(OUT / f"{video}.gif", [f[::2, ::2] for f in frames[::3]], duration=0.1, loop=0)
        imageio.imwrite(OUT / f"{video}_frame.png", frames[-1])
    return moved, peak_force, peak_torque


def max_load(p, mass_kg, cells):
    """이 조합이 밀 수 있는 가장 무거운 짐 (5초 동안 5cm 이상 움직이면 '민다')."""
    lo, hi = 0.0, 60.0
    while hi - lo > 0.1:
        mid = (lo + hi) / 2
        moved, _, _ = run(p, mass_kg, [("t", cells, mid, 0.0)], duration=5.0)
        lo, hi = (mid, hi) if moved["t"] > 0.05 else (lo, mid)
    return lo


def main():
    p = m.Params()
    OUT.mkdir(exist_ok=True)
    mass_kg = m.mass_summary(m.make_parts(p))[0] / 1000

    single = [(0, 0)]
    square = [(0, 0), (1, 0), (0, 1), (1, 1)]
    lanes = [("solo", single, LOAD_KG, 0.0), ("team", square, LOAD_KG, 0.45)]
    moved, force, torque = run(p, mass_kg, lanes, video="sim_push")
    print(f"짐 {LOAD_KG} kg: 1대는 {moved['solo'] * 100:.1f} cm, 4대는 {moved['team'] * 100:.1f} cm 이동")
    print(f"4대 합체 시 결합부에 걸린 최대 힘 {force:.1f} N, 최대 비틀림 {torque:.2f} N·m")

    shapes = {"1대": single, "2대 (앞뒤)": [(0, 0), (1, 0)], "4대 (2 x 2)": square,
              "9대 (3 x 3)": [(i, j) for i in range(3) for j in range(3)]}
    table = []
    for name, cells in shapes.items():
        n = len(cells)
        sim = max_load(p, mass_kg, cells)
        estimate = MU_WHEEL * n * mass_kg / MU_LOAD
        table.append({"shape": name, "modules": n, "sim_max_load_kg": round(sim, 1),
                      "estimate_max_load_kg": round(estimate, 1)})
        print(f"  {name}: 밀 수 있는 짐 {sim:.1f} kg (단순 계산 {estimate:.1f} kg)")

    (OUT / "sim_results.json").write_text(json.dumps({
        "assumptions": {"mu_wheel": MU_WHEEL, "mu_load": MU_LOAD, "mu_face": MU_FACE, "motor_torque_Nm": MOTOR_TORQUE,
                        "module_mass_kg": round(mass_kg, 3), "rigid_joints": True},
        "video": {"load_kg": LOAD_KG, "moved_m": moved, "peak_joint_force_N": round(force, 1),
                  "peak_joint_torque_Nm": round(torque, 2)},
        "max_load_by_shape": table,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
