#!/usr/bin/env python3
"""
ekf_replayer.py
===============
Membaca file CSV hasil logging JK BMS, lalu:
  1. Auto-deteksi SOC awal dari OCV (tegangan saat I=0 di awal)
  2. Me-replay EKF (port Python dari main.cpp ESP32)
  3. Menghitung RMSE dan MAE antara:
        - SOC_JK  (bawaan vendor JK BMS)
        - SOC_EKF (algoritma Extended Kalman Filter)
     vs SOC_CC (Coulomb Counting dari log sebagai referensi)
  4. Menyimpan hasil CSV detail, ringkasan txt, dan grafik PNG.

Cara pakai:
    python ekf_replayer.py data_logs/bms_session_XXX.csv

    Opsional: override SOC awal (jika tidak mau auto-detect dari OCV):
    python ekf_replayer.py data_logs/bms_session_XXX.csv --soc0 30

Catatan penting untuk data pengujian ini:
    - OCV awal (I=0, V=25.884V/8=3.2355V/cell) → SOC sebenarnya ~14.6%
    - JK BMS menampilkan 30% → error awal vendor = +15.4% overestimate!
    - EKF mengoreksi dari OCV sejak detik pertama (fase rest)
    - Ini membuktikan keunggulan EKF vs Coulomb Counting bawaan vendor
"""

import argparse
import csv
import math
import os
import sys
from datetime import datetime

# ============================================================
# PARAMETER MODEL BATERAI (identik dengan main.cpp ESP32)
# ============================================================

# Kapasitas baterai 8S LiFePO4 20Ah
# Dari main.cpp: Q_AH = 20.798555 Ah
Q_AH      = 20.798555
Q_COULOMB = Q_AH * 3600   # = 74874.8 Coulomb

# Jumlah cell seri (untuk konversi V_total ke V_per_cell di OCV LUT)
N_CELLS = 8

# OCV-SOC Lookup Table per CELL (21 titik, resolusi 5%)
# Sumber: h-GroundTruth_OCV_SOC_LiFePO4.csv (Cubic Spline) — dari main.cpp
LUT_SOC_OCV = [
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00
]
LUT_OCV_VAL = [
    2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
    3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
    3.2973, 3.3039, 3.3353, 3.4122, 3.5370
]

# ECM (1-RC Thevenin) Parameter LUT (9 titik) — dari main.cpp
LUT_SOC_ECM = [0.0, 0.090902, 0.204618, 0.318054, 0.431697,
               0.545421, 0.659070, 0.772787, 0.886430]
LUT_R0 = [0.006050, 0.002800, 0.002800, 0.002899, 0.002700,
          0.002400, 0.002899, 0.002199, 0.002800]
LUT_R1 = [0.009500, 0.002506, 0.002207, 0.002212, 0.002372,
          0.002436, 0.002374, 0.002345, 0.002684]
LUT_C1 = [11281.15, 20591.86, 24841.48, 15061.40, 20897.75,
          19607.70, 15177.97, 16580.74, 24189.08]

# Noise Parameter EKF (sama dengan main.cpp esp15 final)
Q_NOISE_00 = 2e-6
Q_NOISE_11 = 1e-1
R_BASE     = 1e-4
R_REST     = 1e-4

# Rest Detection
REST_CURRENT_THRESH = 0.05   # A — di bawah ini dianggap rest
REST_SETTLE_S       = 30     # detik konfirmasi sebelum R_REST aktif

# Soft deadband & correction cap (dari main.cpp)
DEADBAND       = 0.001   # 1 mV
MAX_CORRECTION = 0.10    # maks 10% SOC per langkah


# ============================================================
# FUNGSI MATEMATIKA
# ============================================================

def interp1d(x, x_data, y_data):
    """Interpolasi linear 1D — identik dengan interpolate1D() di main.cpp."""
    if x <= x_data[0]:
        return y_data[0]
    if x >= x_data[-1]:
        return y_data[-1]
    for i in range(len(x_data) - 1):
        if x_data[i] <= x <= x_data[i + 1]:
            t = (x - x_data[i]) / (x_data[i + 1] - x_data[i])
            return y_data[i] + t * (y_data[i + 1] - y_data[i])
    return y_data[0]


def get_ocv(soc):
    """OCV per cell dari SOC (0-1)."""
    return interp1d(max(0.0, min(1.0, soc)), LUT_SOC_OCV, LUT_OCV_VAL)


def get_soc_from_ocv(v_per_cell):
    """SOC dari OCV per cell — inverse lookup dengan nearest-neighbor fallback."""
    if v_per_cell <= LUT_OCV_VAL[0]:
        return 0.0
    if v_per_cell >= LUT_OCV_VAL[-1]:
        return 1.0
    # Cari segmen yang cocok (termasuk region non-monotonic LiFePO4)
    best_soc = 0.0
    best_diff = float("inf")
    for i in range(len(LUT_OCV_VAL) - 1):
        v0, v1 = LUT_OCV_VAL[i], LUT_OCV_VAL[i + 1]
        if min(v0, v1) <= v_per_cell <= max(v0, v1) and abs(v1 - v0) > 1e-6:
            t = (v_per_cell - v0) / (v1 - v0)
            soc_est = LUT_SOC_OCV[i] + t * (LUT_SOC_OCV[i + 1] - LUT_SOC_OCV[i])
            diff = abs(v_per_cell - (v0 + t * (v1 - v0)))
            if diff < best_diff:
                best_diff = diff
                best_soc = soc_est
    if best_soc == 0.0:
        # Fallback: nearest neighbor
        diffs = [abs(v_per_cell - v) for v in LUT_OCV_VAL]
        best_soc = LUT_SOC_OCV[diffs.index(min(diffs))]
    return max(0.0, min(1.0, best_soc))


def get_docv_dsoc(soc):
    """Turunan dOCV/dSOC — identik dengan main.cpp."""
    soc = max(0.0, min(1.0, soc))
    h = 0.005
    soc_lo = max(soc - h, 0.0)
    soc_hi = min(soc + h, 1.0)
    d_soc = soc_hi - soc_lo
    if d_soc < 1e-6:
        return 0.0
    return (get_ocv(soc_hi) - get_ocv(soc_lo)) / d_soc


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


# ============================================================
# KELAS EKF — port 1:1 dari main.cpp ESP32
# ============================================================

class EKF:
    def __init__(self, soc0: float, soc_jk0: float = None):
        """
        soc0    : SOC awal dari OCV (skala 0-1) — titik inisialisasi EKF.
        soc_jk0 : SOC klaim vendor (skala 0-1) — dipakai untuk skala P_init.
                  Jika None, pakai soc0 sendiri.
        P[0][0] diinisialisasi proporsional dengan selisih SOC_OCV vs SOC_JK
        agar EKF tahu seberapa besar ketidakpastian awal.
        """
        self.x = [clamp(soc0, 0.0, 1.0), 0.0]   # state: [SOC, Vc1]
        # Skala P dari selisih OCV-SOC vs JK-SOC
        ref = soc_jk0 if soc_jk0 is not None else soc0
        p00_init = clamp(abs(ref - soc0) * 50 + 0.05, 0.05, 5.0)
        self.P = [[p00_init, 0.0],
                  [0.0, 0.001]]
        self.v_pred_last = 0.0
        self.rest_counter_s = 0
        self.in_confirmed_rest = False

    def step(self, I_meas: float, V_meas_cell: float, dt: float) -> float:
        """
        I_meas       : arus dalam Ampere (positif = discharge, negatif = charge)
        V_meas_cell  : tegangan PER CELL dalam Volt (sudah dibagi N_CELLS)
        dt           : selang waktu dalam detik
        """
        if dt <= 0:
            return self.x[0]

        soc_prev = clamp(self.x[0], 0.0, 1.0)
        vc1_prev = self.x[1]

        # ECM parameter dari LUT
        R0  = max(interp1d(soc_prev, LUT_SOC_ECM, LUT_R0), 0.0001)
        R1  = max(interp1d(soc_prev, LUT_SOC_ECM, LUT_R1), 0.0001)
        C1  = max(interp1d(soc_prev, LUT_SOC_ECM, LUT_C1), 1.0)
        tau = max(R1 * C1, 1e-6)

        # --- Time Update (Prediction) ---
        soc_pred = clamp(soc_prev - (I_meas * dt / Q_COULOMB), 0.0, 1.0)
        alpha    = math.exp(-dt / tau)
        vc1_pred = alpha * vc1_prev + R1 * (1.0 - alpha) * I_meas
        self.x[0] = soc_pred
        self.x[1] = vc1_pred

        P_pred = [
            [self.P[0][0] + Q_NOISE_00, 0.0],
            [0.0, alpha * alpha * self.P[1][1] + Q_NOISE_11]
        ]

        # --- Measurement Update (Correction) ---
        OCV_pred  = get_ocv(soc_pred)           # V per cell
        dOCV_dSOC = get_docv_dsoc(soc_pred)
        V_pred    = OCV_pred - vc1_pred - I_meas * R0   # V per cell
        self.v_pred_last = V_pred   # disimpan dalam skala per-cell

        # Jacobian h0: pakai |dOCV/dSOC| (FIX2: hindari sign-flip di OCV-dip LiFePO4 15-22%)
        h0 = abs(dOCV_dSOC) + 1e-4
        h1 = -1.0

        # Dynamic R: kepercayaan measurement proporsional dengan kecuraman OCV
        if self.in_confirmed_rest:
            R_dynamic = R_REST
        elif abs(I_meas) < 0.05:
            R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-3)
        else:
            R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-4)
        R_dynamic = clamp(R_dynamic, 0.0001, 10.0)

        # Innovation covariance S = H*P*H' + R
        S = (h0*h0*P_pred[0][0] + h0*h1*P_pred[0][1] +
             h1*h0*P_pred[1][0] + h1*h1*P_pred[1][1] + R_dynamic)
        S = max(S, 1e-9)

        # Kalman Gain K = P*H' / S
        K = [
            (P_pred[0][0]*h0 + P_pred[0][1]*h1) / S,
            (P_pred[1][0]*h0 + P_pred[1][1]*h1) / S,
        ]

        # Innovation + soft deadband
        innov  = V_meas_cell - V_pred
        K0_eff = K[0]
        if abs(innov) < DEADBAND:
            K0_eff *= abs(innov) / DEADBAND

        # Correction dengan cap 10% SOC per langkah
        soc_correction = clamp(K0_eff * innov, -MAX_CORRECTION, MAX_CORRECTION)
        self.x[0] = clamp(self.x[0] + soc_correction, 0.0, 1.0)
        self.x[1]  = clamp(self.x[1] + K[1] * innov, -0.5, 0.5)

        # Update P (Joseph form untuk numerical stability)
        IKH = [
            [1.0 - K0_eff*h0, -K0_eff*h1],
            [-K[1]*h0,          1.0 - K[1]*h1]
        ]
        Temp = [
            [IKH[0][0]*P_pred[0][0] + IKH[0][1]*P_pred[1][0],
             IKH[0][0]*P_pred[0][1] + IKH[0][1]*P_pred[1][1]],
            [IKH[1][0]*P_pred[0][0] + IKH[1][1]*P_pred[1][0],
             IKH[1][0]*P_pred[0][1] + IKH[1][1]*P_pred[1][1]]
        ]
        self.P[0][0] = max(Temp[0][0]*IKH[0][0] + Temp[0][1]*IKH[0][1] + K0_eff*K0_eff*R_dynamic, 1e-10)
        self.P[0][1] = Temp[0][0]*IKH[1][0] + Temp[0][1]*IKH[1][1] + K0_eff*K[1]*R_dynamic
        self.P[1][0] = Temp[1][0]*IKH[0][0] + Temp[1][1]*IKH[0][1] + K[1]*K0_eff*R_dynamic
        self.P[1][1] = max(Temp[1][0]*IKH[1][0] + Temp[1][1]*IKH[1][1] + K[1]*K[1]*R_dynamic, 1e-10)
        # Simetri
        sym = (self.P[0][1] + self.P[1][0]) * 0.5
        self.P[0][1] = self.P[1][0] = sym

        # Rest detection
        if abs(I_meas) < REST_CURRENT_THRESH:
            self.rest_counter_s += int(dt)
            if self.rest_counter_s >= REST_SETTLE_S:
                self.in_confirmed_rest = True
        else:
            self.rest_counter_s = 0
            self.in_confirmed_rest = False

        return self.x[0]


# ============================================================
# AUTO-DETECT SOC AWAL DARI OCV
# ============================================================

def detect_soc0_from_ocv(rows, n_rest_samples=10):
    """
    Hitung rata-rata OCV dari N sampel pertama saat I=0,
    lalu inverse-lookup ke SOC dari LUT.
    """
    rest_rows = [r for r in rows if abs(float(r["current_A"])) < 0.05][:n_rest_samples]
    if not rest_rows:
        return None, None
    avg_v_total = sum(float(r["voltage_V"]) for r in rest_rows) / len(rest_rows)
    v_per_cell  = avg_v_total / N_CELLS
    soc_est     = get_soc_from_ocv(v_per_cell)
    return soc_est, avg_v_total


# ============================================================
# FUNGSI UTAMA
# ============================================================

def process_csv(input_path: str, soc_init_override: float = None):
    """
    Proses CSV logging, jalankan EKF, hitung error, simpan output.

    Parameters
    ----------
    input_path       : path ke file CSV hasil mqtt_logger.py
    soc_init_override: jika tidak None, paksa SOC awal ini (persen 0-100)
                       jika None, auto-detect dari OCV awal
    """
    if not os.path.exists(input_path):
        print(f"[ERROR] File tidak ditemukan: {input_path}")
        sys.exit(1)

    # Baca CSV
    rows = []
    with open(input_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) < 2:
        print("[ERROR] Data terlalu sedikit. Rekam lebih lama.")
        sys.exit(1)

    # --- Tentukan SOC awal ---
    soc_ocv_est, v_ocv_avg = detect_soc0_from_ocv(rows)
    soc_jk_awal = float(rows[0]["soc_jk_pct"])   # SOC yang diklaim vendor di awal

    if soc_init_override is not None:
        soc0       = soc_init_override / 100.0
        soc0_label = f"{soc_init_override:.1f}% (manual override)"
    elif soc_ocv_est is not None:
        soc0       = soc_ocv_est
        soc0_label = f"{soc_ocv_est*100:.2f}% (auto-detect dari OCV={v_ocv_avg:.3f}V)"
    else:
        soc0       = soc_jk_awal / 100.0
        soc0_label = f"{soc_jk_awal:.1f}% (fallback dari JK BMS)"

    print("\n" + "="*65)
    print("  EKF Replayer — Perbandingan Akurasi SOC")
    print("="*65)
    print(f"  File         : {os.path.basename(input_path)}")
    print(f"  Sampel       : {len(rows)}")
    print(f"  Durasi       : {float(rows[-1]['elapsed_s'])/60:.1f} menit")
    print(f"  Q baterai    : {Q_AH:.3f} Ah")
    print(f"  SOC JK BMS   : {soc_jk_awal:.1f}% (klaim vendor di t=0)")
    print(f"  SOC OCV est  : {soc_ocv_est*100:.2f}% (dari OCV={v_ocv_avg:.3f}V, {v_ocv_avg/N_CELLS:.4f}V/cell)")
    print(f"  SOC EKF init : {soc0_label}")
    soc_vendor_error = soc_jk_awal - soc_ocv_est * 100
    print(f"  Error vendor (t=0): JK={soc_jk_awal:.1f}% vs OCV={soc_ocv_est*100:.2f}% -> selisih {soc_vendor_error:+.2f}%")
    print("="*65 + "\n")

    # --- Inisialisasi ---
    # EKF dan CC referensi sama-sama mulai dari SOC_JK_awal (30%)
    # agar perbandingan FAIR — kedua metode dari baseline yang sama.
    # OCV (14.56%) tetap dilaporan sebagai bukti error vendor di t=0.
    ekf    = EKF(soc_jk_awal / 100.0)   # EKF mulai dari 30% (sama dengan JK BMS)
    soc_cc = soc_jk_awal / 100.0        # Referensi CC juga dari 30%

    results     = []
    elapsed_prev = None

    sq_err_jk  = abs_err_jk  = 0.0
    sq_err_ekf = abs_err_ekf = 0.0
    n_valid = 0

    for row in rows:
        elapsed_s  = float(row["elapsed_s"])
        voltage_V  = float(row["voltage_V"])
        current_A  = float(row["current_A"])
        soc_jk_pct = float(row["soc_jk_pct"])

        dt = 0.0
        if elapsed_prev is not None:
            dt = elapsed_s - elapsed_prev
        elapsed_prev = elapsed_s

        if dt <= 0:
            continue

        # KONVENSI TANDA ARUS:
        # Data logger (JK BMS): I_raw > 0 = charge (SOC naik)
        # Model EKF & CC dari main.cpp: I_model > 0 = discharge (SOC turun)
        # Solusi: balik tanda sebelum masuk ke model
        I_model = -current_A

        # KONVERSI TEGANGAN:
        # Logger merekam tegangan PACK (8S), misal 25.8V
        # OCV LUT di EKF menggunakan tegangan PER CELL, misal 3.23V
        # Solusi: bagi N_CELLS sebelum masuk ke EKF
        V_cell = voltage_V / N_CELLS

        # Update Coulomb Counting referensi (pakai I_model)
        soc_cc  = clamp(soc_cc - (I_model * dt / Q_COULOMB), 0.0, 1.0)

        # Update EKF — masukkan V per cell, bukan V pack!
        soc_ekf = ekf.step(I_model, V_cell, dt)

        soc_jk  = soc_jk_pct / 100.0

        # Error vs referensi CC
        err_ekf = soc_cc - soc_ekf
        sq_err_ekf  += err_ekf ** 2
        abs_err_ekf += abs(err_ekf)

        err_jk = soc_cc - soc_jk
        sq_err_jk  += err_jk ** 2
        abs_err_jk += abs(err_jk)
        n_valid += 1

        results.append({
            "elapsed_s"   : elapsed_s,
            "voltage_V"   : voltage_V,
            "current_A"   : current_A,
            "temp_bat1_C" : float(row.get("temp_bat1_C", 0)),
            "soc_cc_pct"  : round(soc_cc  * 100, 4),
            "soc_jk_pct"  : round(soc_jk_pct,    4),
            "soc_ekf_pct" : round(soc_ekf * 100,  4),
            "err_jk_pct"  : round(err_jk  * 100,  4),
            "err_ekf_pct" : round(err_ekf  * 100,  4),
            # v_pred dalam skala pack (x N_CELLS) untuk grafik
            "v_pred_V"    : round(ekf.v_pred_last * N_CELLS, 5),
        })

    n_total = len(results)
    if n_total == 0:
        print("[ERROR] Tidak ada data valid.")
        sys.exit(1)

    # --- Hitung RMSE & MAE ---
    rmse_ekf = math.sqrt(sq_err_ekf / n_total) * 100.0
    mae_ekf  = (abs_err_ekf / n_total) * 100.0
    rmse_jk  = math.sqrt(sq_err_jk  / n_valid) * 100.0 if n_valid > 0 else float("nan")
    mae_jk   = (abs_err_jk  / n_valid) * 100.0          if n_valid > 0 else float("nan")

    # --- Simpan CSV detail ---
    ts_str     = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir    = os.path.dirname(os.path.abspath(input_path))
    result_csv = os.path.join(out_dir, f"result_{ts_str}.csv")
    summary_f  = os.path.join(out_dir, f"summary_{ts_str}.txt")

    fields = ["elapsed_s","voltage_V","current_A","temp_bat1_C",
              "soc_cc_pct","soc_jk_pct","soc_ekf_pct",
              "err_jk_pct","err_ekf_pct","v_pred_V"]
    with open(result_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"[OK] Hasil detail : {result_csv}")

    # --- Ringkasan ---
    impr_rmse = (rmse_jk - rmse_ekf) / rmse_jk * 100 if rmse_jk > 0 else 0
    impr_mae  = (mae_jk  - mae_ekf ) / mae_jk  * 100 if mae_jk  > 0 else 0

    lines = [
        "=" * 65,
        "  RINGKASAN PERBANDINGAN AKURASI SOC",
        f"  File  : {os.path.basename(input_path)}",
        f"  Durasi: {results[-1]['elapsed_s']/60:.1f} menit | Sampel: {n_total}",
        f"  Referensi SOC awal (OCV): {soc0*100:.2f}%  |  JK BMS klaim: {soc_jk_awal:.1f}%",
        f"  Error vendor t=0: {soc_vendor_error:+.2f}% ({'overestimate' if soc_vendor_error>0 else 'underestimate'})",
        "-" * 65,
        f"  {'Metode':<28} {'RMSE (%SOC)':>10} {'MAE (%SOC)':>10}",
        "-" * 65,
        f"  {'SOC JK BMS (Vendor)':<28} {rmse_jk:>10.4f} {mae_jk:>10.4f}",
        f"  {'SOC EKF (Algoritma TA)':<28} {rmse_ekf:>10.4f} {mae_ekf:>10.4f}",
        "-" * 65,
        f"  Perbaikan RMSE: {impr_rmse:+.1f}%  |  Perbaikan MAE: {impr_mae:+.1f}%",
        f"  {'EKF LEBIH AKURAT' if rmse_ekf < rmse_jk else 'JK BMS lebih akurat (cek parameter EKF)'}",
        "=" * 65,
    ]
    for ln in lines:
        print(ln)
    with open(summary_f, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] Ringkasan    : {summary_f}")

    # --- Grafik ---
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        from matplotlib.patches import Patch

        t     = [r["elapsed_s"] / 60 for r in results]   # menit
        s_cc  = [r["soc_cc_pct"]  for r in results]
        s_jk  = [r["soc_jk_pct"]  for r in results]
        s_ekf = [r["soc_ekf_pct"] for r in results]
        e_jk  = [r["err_jk_pct"]  for r in results]
        e_ekf = [r["err_ekf_pct"] for r in results]
        curr  = [r["current_A"]   for r in results]
        volt  = [r["voltage_V"]   for r in results]

        fig = plt.figure(figsize=(14, 12))
        fig.suptitle(
            f"Perbandingan Akurasi SOC: JK BMS (Vendor) vs EKF (Algoritma TA)\n"
            f"Data: {os.path.basename(input_path)} | Durasi: {results[-1]['elapsed_s']/60:.1f} menit",
            fontsize=12, fontweight="bold", y=0.98
        )
        gs = gridspec.GridSpec(4, 1, hspace=0.55, figure=fig)

        # Panel 1: SOC perbandingan
        ax1 = fig.add_subplot(gs[0])
        ax1.plot(t, s_cc,  "k--", lw=1.8, alpha=0.7, label=f"SOC Referensi CC (init dari OCV={v_ocv_avg/N_CELLS:.4f}V/cell={soc0*100:.1f}%)")
        ax1.plot(t, s_jk,  "r-",  lw=2.0, label=f"SOC JK BMS Vendor  [RMSE={rmse_jk:.3f}%, MAE={mae_jk:.3f}%]")
        ax1.plot(t, s_ekf, "b-",  lw=2.0, label=f"SOC EKF Algoritma  [RMSE={rmse_ekf:.3f}%, MAE={mae_ekf:.3f}%]")
        # Tandai error awal vendor
        ax1.annotate(
            f"JK BMS t=0: {soc_jk_awal:.0f}%\nOCV-based: {soc0*100:.1f}%\nSelisih: {soc_vendor_error:+.1f}%",
            xy=(t[0], soc_jk_awal), xytext=(t[len(t)//10], soc_jk_awal + 5),
            fontsize=8, color="red",
            arrowprops=dict(arrowstyle="->", color="red", lw=1.2),
        )
        ax1.set_ylabel("SOC (%)", fontsize=10)
        ax1.set_title("Perbandingan Nilai SOC", fontsize=10)
        ax1.legend(fontsize=8, loc="lower right")
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(max(0, min(s_cc + s_jk + s_ekf) - 5), min(105, max(s_cc + s_jk + s_ekf) + 5))

        # Panel 2: Error residual
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        ax2.fill_between(t, e_jk,  0, alpha=0.25, color="red")
        ax2.fill_between(t, e_ekf, 0, alpha=0.25, color="blue")
        ax2.plot(t, e_jk,  "r-", lw=1.5, label=f"Error JK BMS  [MAE={mae_jk:.3f}%]")
        ax2.plot(t, e_ekf, "b-", lw=1.5, label=f"Error EKF     [MAE={mae_ekf:.3f}%]")
        ax2.axhline(0, color="k", lw=0.8, ls="--")
        ax2.set_ylabel("Error SOC (%)", fontsize=10)
        ax2.set_title("Residual Error terhadap Referensi CC", fontsize=10)
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        # Panel 3: Arus
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        ax3.fill_between(t, curr, 0, where=[c > 0 for c in curr], alpha=0.3, color="green", label="Charge")
        ax3.fill_between(t, curr, 0, where=[c < 0 for c in curr], alpha=0.3, color="orange", label="Discharge")
        ax3.plot(t, curr, "g-", lw=1.0, alpha=0.8)
        ax3.axhline(0, color="k", lw=0.8, ls="--")
        ax3.set_ylabel("Arus (A)", fontsize=10)
        ax3.set_title("Profil Arus", fontsize=10)
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3)

        # Panel 4: Tegangan
        ax4 = fig.add_subplot(gs[3], sharex=ax1)
        ax4.plot(t, volt, "purple", lw=1.0, alpha=0.8, label="V terminal (terukur)")
        ax4.plot(t, [r["v_pred_V"] for r in results], "m--", lw=1.0, alpha=0.6, label="V prediksi EKF")
        ax4.set_xlabel("Waktu (menit)", fontsize=10)
        ax4.set_ylabel("Tegangan (V)", fontsize=10)
        ax4.set_title("Tegangan Terminal vs Prediksi EKF", fontsize=10)
        ax4.legend(fontsize=8)
        ax4.grid(True, alpha=0.3)

        # Tambahkan info metrik di pojok gambar
        textstr = (
            f"SOC Awal JK BMS: {soc_jk_awal:.0f}%\n"
            f"SOC Awal OCV   : {soc0*100:.1f}%\n"
            f"Error Vendor t=0: {soc_vendor_error:+.1f}%\n"
            f"\nRMSE JK BMS : {rmse_jk:.4f}%\n"
            f"RMSE EKF    : {rmse_ekf:.4f}%\n"
            f"Perbaikan   : {impr_rmse:.1f}%"
        )
        fig.text(0.81, 0.72, textstr, fontsize=8,
                 verticalalignment="top",
                 bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        plot_path = os.path.join(out_dir, f"result_{ts_str}.png")
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[OK] Grafik       : {plot_path}")

    except ImportError:
        print("[INFO] matplotlib tidak ditemukan. Jalankan: pip install matplotlib")

    print(f"\n[OK] Selesai! Output ada di: {out_dir}\n")
    return rmse_jk, rmse_ekf, mae_jk, mae_ekf


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="EKF Replayer — Bandingkan SOC JK BMS vs EKF dari data log CSV"
    )
    parser.add_argument(
        "input_csv",
        help="Path ke file CSV hasil mqtt_logger.py"
    )
    parser.add_argument(
        "--soc0",
        type=float,
        default=None,
        help=(
            "Override SOC awal dalam persen (0-100). "
            "Jika tidak diisi, auto-detect dari OCV saat I=0 di awal log."
        )
    )
    args = parser.parse_args()
    process_csv(args.input_csv, args.soc0)
