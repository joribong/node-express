"""결합부가 버텨야 하는 힘 계산.

실행:  python robot-cad/joint_loads.py
결과:  out/joint_loads.csv

핀과 구멍은 끼워 맞춤이라 옆으로 밀리는 힘(전단)만 받는다.
당기는 힘은 면 가운데의 자석 또는 잠금장치가 받아야 한다.
굽힘은 "면 아래 모서리를 받침점으로, 가운데 잠금장치가 당겨 버티는" 것으로 본 단순 계산이다.
"""

import csv
import json

import module1 as m

G = 9.81


def main():
    p = m.Params()
    mass = m.mass_summary(m.make_parts(p))[0] / 1000          # kg
    weight = mass * G                                          # N
    L = p.length / 1000
    arm = p.height / 2 / 1000                                  # 아래 모서리에서 가운데 잠금장치까지

    rows = [("상황", "결합부 전단력_N", "결합부 굽힘_N·m", "잠금장치가 당겨 버틸 힘_N", "설명")]

    try:
        sim = json.loads((m.OUT / "sim_results.json").read_text(encoding="utf-8"))["video"]
        rows.append((f"4대가 {sim['load_kg']:g} kg 짐 밀기 (시뮬레이션)", sim["peak_joint_force_N"],
                     sim["peak_joint_torque_Nm"], round(sim["peak_joint_torque_Nm"] / arm),
                     "시뮬레이션 최댓값. 굽힘을 모두 잠금장치가 받는다고 본 값"))
    except (OSError, KeyError):
        pass

    for k in (1, 2, 3):
        moment = sum(weight * (i - 0.5) * L for i in range(1, k + 1))
        rows.append((f"틈 건너기: {k}대가 허공에 뜸", round(k * weight, 1), round(moment, 2), round(moment / arm),
                     "일렬로 붙어 바닥의 틈을 건널 때 가장 안쪽 결합부"))
    for k in (1, 2):
        rows.append((f"매달기: {k}대를 수직으로 끌어올림", 0, 0, round(k * weight, 1),
                     "턱 위의 모듈이 아래 모듈을 끌어올릴 때"))

    m.OUT.mkdir(exist_ok=True)
    with open(m.OUT / "joint_loads.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    print(f"모듈 1대 무게 {mass:.2f} kg ({weight:.1f} N), 잠금장치 팔 길이 {arm * 1000:.0f} mm")
    for r in rows:
        print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
