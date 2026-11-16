"""결합부 잠금장치가 버텨야 하는 힘과 버틸 수 있는 힘.

실행:  python robot-cad/joint_loads.py
결과:  out/joint_loads.csv, out/joint_loads.json

핀과 구멍은 끼워 맞춤이라 옆으로 밀리는 힘(전단)만 받는다.
당기는 힘은 잠금 볼트가 받는다. 굽힘은 "면의 한쪽 모서리를 받침점으로, 잠금 볼트가 당겨 버티는"
단순 계산이다. 충격은 넣지 않았다. 허용 응력은 가정값이며 시험으로 확인해야 한다.
"""

import csv
import json
import math

import module1 as m

G = 9.81
# 허용 응력 (MPa = N/mm2). 가정값.
ABS_BEARING = 20     # 수지 벽이 눌리는 힘
ABS_SHEAR = 12       # 수지 벽이 뜯겨 나가는 힘
STEEL_BEND = 150     # 강재 볼트 머리의 굽힘
STEEL_TENSION = 150  # 강재 축의 인장


def capacity(p):
    """잠금 볼트 1개가 버틸 수 있는 힘과 어느 부분이 먼저 한계에 닿는지."""
    slot_half = (p.latch_head_w + 0.8) / 2                 # 세로 홈의 절반 폭 (이 부분은 벽이 없다)
    lug = p.latch_head_len / 2 - slot_half                 # 벽에 실제로 걸리는 길이 (한쪽)
    area = 2 * lug * p.latch_head_w
    perimeter = 2 * (2 * lug + p.latch_head_w)
    arm = (slot_half + p.latch_head_len / 2) / 2 - p.latch_shaft_r
    section = p.latch_head_w * p.latch_head_t ** 2 / 6
    collar = math.pi * (p.latch_collar_r ** 2 - (p.latch_shaft_r + 0.2) ** 2)
    limits = {
        "상대 벽 눌림 (ABS)": area * ABS_BEARING,
        "상대 벽 뜯김 (ABS)": perimeter * p.latch_wall * ABS_SHEAR,
        "볼트 머리 굽힘 (강재)": 2 * STEEL_BEND * section / arm,
        "자기 벽의 턱 눌림 (ABS)": collar * ABS_BEARING,
        "볼트 축 인장 (강재)": math.pi * p.latch_shaft_r ** 2 * STEEL_TENSION,
    }
    name = min(limits, key=limits.get)
    return limits[name], name, limits


def compute(p):
    mass = m.mass_summary(m.make_parts(p))[0] / 1000
    weight = mass * G
    L = p.length / 1000
    arm_sag = (p.height / 2 + p.latch_dy) / 1000     # 아래로 처질 때: 아래 모서리가 받침점
    arm_hog = (p.height / 2 - p.latch_dy) / 1000     # 위로 꺾일 때: 위 모서리가 받침점
    cap, limit, limits = capacity(p)

    cases = []

    def add(name, required, note):
        cases.append({"name": name, "required_N": round(required, 1), "sf_single": round(cap / required, 1),
                      "sf_double": round(2 * cap / required, 1), "note": note})

    try:
        sim = json.loads((m.OUT / "sim_results.json").read_text(encoding="utf-8"))["video"]
        add(f"4대가 {sim['load_kg']:g} kg 짐 밀기", sim["peak_joint_torque_Nm"] / arm_hog,
            "시뮬레이션 최대 비틀림을 불리한 쪽 팔 길이로 나눈 값")
    except (OSError, KeyError):
        pass
    for k in (1, 2, 3):
        moment = sum(weight * (i - 0.5) * L for i in range(1, k + 1))
        add(f"틈 건너기: {k}대가 허공에 뜸 (아래로 처짐)", moment / arm_sag, "일렬로 붙어 바닥의 틈을 건널 때 가장 안쪽 결합부")
    for k in (1, 2, 3):
        moment = sum(weight * (i - 0.5) * L for i in range(1, k + 1))
        add(f"턱 넘기: 양쪽 {k}대씩 뜸 (위로 꺾임)", moment / arm_hog, "가운데가 턱에 얹혀 양쪽이 뜰 때. 볼트가 위쪽에 있어 불리하다")
    for k in (1, 2):
        add(f"매달기: {k}대를 수직으로 끌어올림", k * weight, "턱 위의 모듈이 아래 모듈을 끌어올릴 때")
    return {"module_mass_kg": round(mass, 3), "arm_sag_mm": arm_sag * 1000, "arm_hog_mm": arm_hog * 1000,
            "capacity_N": round(cap), "limit": limit, "limits_N": {k: round(v) for k, v in limits.items()},
            "allowable_MPa": {"abs_bearing": ABS_BEARING, "abs_shear": ABS_SHEAR, "steel_bend": STEEL_BEND,
                              "steel_tension": STEEL_TENSION},
            "cases": cases}


def main():
    p = m.Params()
    r = compute(p)
    m.OUT.mkdir(exist_ok=True)
    (m.OUT / "joint_loads.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(m.OUT / "joint_loads.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(("상황", "잠금 볼트가 버틸 힘_N", "안전율_볼트 1개", "안전율_볼트 2개", "설명"))
        for c in r["cases"]:
            w.writerow((c["name"], c["required_N"], c["sf_single"], c["sf_double"], c["note"]))
    print(f"모듈 1대 {r['module_mass_kg']} kg. 팔 길이: 처짐 {r['arm_sag_mm']:.0f} mm, 꺾임 {r['arm_hog_mm']:.0f} mm")
    print("볼트 1개가 버티는 힘 (부분별):")
    for k, v in r["limits_N"].items():
        print(f"  {k}: {v} N")
    print(f"→ 가장 약한 곳: {r['limit']}, 허용 {r['capacity_N']} N")
    for c in r["cases"]:
        print(f"  {c['name']}: 필요 {c['required_N']} N, 안전율 {c['sf_single']} (1개) / {c['sf_double']} (2개)")


if __name__ == "__main__":
    main()
