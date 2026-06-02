"""
preprocess.py — Deterministic Current-Direction Resolver for ZKETECH Data

Resolves the absolute-current ambiguity from the ZKETECH load tester
using an edge-triggered state machine. Only evaluates voltage shift (ΔV)
at the exact rest→active transition to lock current direction.

Output: Time(S),Dir_Cur(A),Vol(V)
  - Positive Dir_Cur = Discharge (SOC decreasing)
  - Negative Dir_Cur = Charge   (SOC increasing)
  - Zero Dir_Cur     = Rest
"""

import csv
import os
import sys

CURRENT_THRESHOLD = 0.05  # Amps — below this is considered rest

INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

DATASETS = [
    "h-charge_rest_60m.csv",
    "h-DCC-4.4A-2.5V.csv",
    "h-Dynamic_Profiling_(Urban Load).csv",
    "h-charging_7.33A-rest 2h.csv",
    "h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv",
]


def preprocess(input_path: str, output_path: str) -> dict:
    """
    Process a single dataset with edge-triggered sign detection.

    State machine:
        state  0 = Rest
        state  1 = Discharge (positive current, SOC drops)
        state -1 = Charge    (negative current, SOC rises)

    Transition logic:
        Only at the exact sample where current crosses from ≤ threshold
        to > threshold, evaluate ΔV = V_t - V_{t-1}.
          ΔV > 0  →  Charging  (state = -1)
          ΔV ≤ 0  →  Discharging (state = 1)
        State is locked until current falls back to ≤ threshold.
    """
    rows_in = []
    with open(input_path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 3:
                continue
            # Skip malformed rows (contain '*' or '-' artifact markers)
            raw = ",".join(row)
            if "*" in raw or (
                "-" in raw
                and not any(c.isdigit() for c in raw.split(",")[0])
            ):
                continue
            try:
                t = float(row[0].strip())
                i = float(row[1].strip())
                v = float(row[2].strip())
                rows_in.append((t, i, v))
            except ValueError:
                continue

    rows_out = []
    state = 0  # 0=Rest, 1=Discharge, -1=Charge
    v_prev = None
    stats = {"rest": 0, "charge": 0, "discharge": 0, "transitions": 0}

    for idx, (t, i_abs, v) in enumerate(rows_in):
        if i_abs <= CURRENT_THRESHOLD:
            # Rest period
            if state != 0:
                stats["transitions"] += 1
            state = 0
            dir_cur = 0.0
            stats["rest"] += 1
        else:
            # Active period
            if state == 0:
                # Edge trigger: transitioning from rest to active
                if v_prev is not None:
                    delta_v = v - v_prev
                    if delta_v > 0:
                        state = -1  # Charging
                    else:
                        state = 1  # Discharging
                else:
                    # No previous voltage reference (first sample is active)
                    # Default to discharge
                    state = 1
                stats["transitions"] += 1

            # Apply locked sign
            if state == -1:
                dir_cur = -abs(i_abs)
                stats["charge"] += 1
            else:
                dir_cur = abs(i_abs)
                stats["discharge"] += 1

        v_prev = v
        rows_out.append((t, dir_cur, v))

    # Write output
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Time(S)", "Dir_Cur(A)", "Vol(V)"])
        for t, dc, v in rows_out:
            writer.writerow([f"{t:.0f}", f"{dc:.2f}", f"{v:.3f}"])

    stats["total"] = len(rows_out)
    return stats


def main():
    print("=" * 70)
    print("  ZKETECH Current-Direction Preprocessor")
    print("  Edge-Triggered State Machine v1.0")
    print("=" * 70)

    for dataset in DATASETS:
        input_path = os.path.join(INPUT_DIR, dataset)
        output_name = f"clean_{dataset}"
        output_path = os.path.join(INPUT_DIR, output_name)

        if not os.path.exists(input_path):
            print(f"\n[SKIP] {dataset} — file not found")
            continue

        print(f"\n[PROCESSING] {dataset}")
        stats = preprocess(input_path, output_path)

        print(f"  -> Output: {output_name}")
        print(f"  -> Samples: {stats['total']}")
        print(f"  -> Rest: {stats['rest']}, "
              f"Charge: {stats['charge']}, "
              f"Discharge: {stats['discharge']}")
        print(f"  -> State transitions: {stats['transitions']}")

    print(f"\n{'=' * 70}")
    print("  Done. Upload clean_*.csv files to ESP32 LittleFS.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
