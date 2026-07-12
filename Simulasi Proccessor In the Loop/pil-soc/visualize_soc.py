"""
visualize_soc.py — Reproduksi Python dari algoritma EKF dan CC di main.cpp (Pengujian 3)
Menghasilkan:
  1. Kurva SoC Riil vs SoC EKF vs SoC CC (satu sumbu waktu)
  2. Grafik batang RMSE variasi Q dan R (tuning analysis)

Dependensi: pip install numpy matplotlib pandas
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MultipleLocator
import os, math

# ─────────────────────────────────────────────────────────────
# 1. KONSTANTA MODEL BATERAI (sama persis dengan main.cpp Pengujian 3)
# ─────────────────────────────────────────────────────────────
Q_COULOMB = 74874.8  # Coulomb

# OCV-SOC LUT
lut_soc_ocv = np.array([0.00,0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,
                         0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95,1.00])
lut_ocv_val = np.array([2.6550,3.0269,3.1972,3.2391,3.2261,3.2242,3.2424,3.2625,
                         3.2758,3.2835,3.2871,3.2880,3.2878,3.2884,3.2917,3.2958,
                         3.2973,3.3039,3.3353,3.4122,3.5370])

# ECM LUT
lut_soc_ecm = np.array([0.0,0.090902,0.204618,0.318054,0.431697,0.545421,0.659070,0.772787,0.886430])
lut_r0      = np.array([0.006050,0.002800,0.002800,0.002899,0.002700,0.002400,0.002899,0.002199,0.002800])
lut_r1      = np.array([0.009500,0.002506,0.002207,0.002212,0.002372,0.002436,0.002374,0.002345,0.002684])
lut_c1      = np.array([11281.15,20591.86,24841.48,15061.40,20897.75,19607.70,15177.97,16580.74,24189.08])

# EKF tuning (Pengujian 3 final)
Q_00  = 2e-6
Q_11  = 1e-1
R_BASE = 1e-4
R_REST = 1e-4
REST_CURRENT_THRESH = 0.05
REST_SETTLE_S = 30

# ─────────────────────────────────────────────────────────────
# 2. FUNGSI HELPER
# ─────────────────────────────────────────────────────────────
def interp1d_lut(x, xs, ys):
    return float(np.interp(x, xs, ys))

def get_ocv(soc):
    return interp1d_lut(np.clip(soc, 0, 1), lut_soc_ocv, lut_ocv_val)

def get_docv_dsoc(soc):
    soc = np.clip(soc, 0, 1)
    h = 0.005
    lo = max(soc - h, 0.0)
    hi = min(soc + h, 1.0)
    dSOC = hi - lo
    if dSOC < 1e-6:
        return 0.0
    return (get_ocv(hi) - get_ocv(lo)) / dSOC

def get_r0(soc):  return max(interp1d_lut(soc, lut_soc_ecm, lut_r0), 1e-4)
def get_r1(soc):  return max(interp1d_lut(soc, lut_soc_ecm, lut_r1), 1e-4)
def get_c1(soc):  return max(interp1d_lut(soc, lut_soc_ecm, lut_c1), 1.0)

# ─────────────────────────────────────────────────────────────
# 3. SIMULATOR EKF (mereproduksi main.cpp runEKFStep)
# ─────────────────────────────────────────────────────────────
class EKFSimulator:
    def __init__(self, soc_init, q00=Q_00, q11=Q_11, r_base=R_BASE, r_rest=R_REST):
        self.x  = np.array([soc_init, 0.0])
        self.P  = np.array([[soc_init*50+0.01, 0.0],[0.0, 0.001]])
        self.q00 = q00
        self.q11 = q11
        self.r_base = r_base
        self.r_rest = r_rest
        self.v_pred = 0.0
        self.rest_counter = 0
        self.in_rest = False

    def step(self, I, V, dt):
        soc_prev = np.clip(self.x[0], 0, 1)
        vc1_prev = self.x[1]
        R0  = get_r0(soc_prev)
        R1  = get_r1(soc_prev)
        C1  = get_c1(soc_prev)
        tau = max(R1*C1, 1e-6)
        soc_pred = np.clip(soc_prev - I*dt/Q_COULOMB, 0, 1)
        alpha    = math.exp(-dt/tau) if dt > 0 else 1.0
        vc1_pred = alpha*vc1_prev + R1*(1-alpha)*I
        self.x = np.array([soc_pred, vc1_pred])

        P_pred = np.array([[self.P[0,0]+self.q00,       0.0],
                           [0.0,  alpha**2*self.P[1,1]+self.q11]])

        OCV_pred  = get_ocv(soc_pred)
        dOCV_dSOC = get_docv_dsoc(soc_pred)
        V_pred    = OCV_pred - vc1_pred - I*R0
        self.v_pred = V_pred

        h0 = abs(dOCV_dSOC) + 1e-4
        h1 = -1.0

        # Dynamic R
        if self.in_rest:
            R_dyn = self.r_rest
        elif abs(I) < 0.05:
            R_dyn = self.r_base / (abs(dOCV_dSOC) + 1e-3)
        else:
            R_dyn = self.r_base / (abs(dOCV_dSOC) + 1e-4)
        R_dyn = np.clip(R_dyn, 1e-4, 10.0)

        S = h0**2*P_pred[0,0] + h0*h1*P_pred[0,1] + h1*h0*P_pred[1,0] + h1**2*P_pred[1,1] + R_dyn
        S = max(S, 1e-9)
        K = np.array([(P_pred[0,0]*h0 + P_pred[0,1]*h1)/S,
                      (P_pred[1,0]*h0 + P_pred[1,1]*h1)/S])

        innov   = V - V_pred
        DEADBAND = 0.001
        MAX_CORR = 0.10
        K0_eff = K[0]
        if abs(innov) < DEADBAND:
            K0_eff *= abs(innov)/DEADBAND
        soc_corr = np.clip(K0_eff*innov, -MAX_CORR, MAX_CORR)
        self.x[0] = np.clip(self.x[0] + soc_corr, 0, 1)
        self.x[1] += K[1]*innov
        self.x[1]  = np.clip(self.x[1], -0.5, 0.5)

        I_KH = np.array([[1-(K0_eff*h0), -(K0_eff*h1)],
                         [-(K[1]*h0),     1-(K[1]*h1)]])
        Temp = I_KH @ P_pred
        self.P = Temp @ I_KH.T + np.array([[K0_eff**2*R_dyn,    K0_eff*K[1]*R_dyn],
                                            [K[1]*K0_eff*R_dyn,  K[1]**2*R_dyn]])
        self.P = (self.P + self.P.T)*0.5
        self.P[0,0] = max(self.P[0,0], 1e-10)
        self.P[1,1] = max(self.P[1,1], 1e-10)

    def update_rest(self, I, dt):
        if abs(I) < REST_CURRENT_THRESH:
            self.rest_counter += int(dt)
            if self.rest_counter >= REST_SETTLE_S:
                self.in_rest = True
        else:
            self.rest_counter = 0
            self.in_rest = False

# ─────────────────────────────────────────────────────────────
# 4. LOAD DATASET
# ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DATASETS = {
    "dataset_dynamic_profiling_urban_load.csv":        ("Dynamic Profiling", 0.953),
    "dataset_dcc_0.22c_discharge_constant_2.5v.csv":   ("DCC Discharge 4.4A", 1.0),
    "dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv":        ("OCV Charge-Rest",    0.0),
    "dataset_fast_charging_0.35c_rest_2h.csv":          ("Fast Charging 7.3A", 0.06),
    "dataset_capacity_measurement_dcc_cc_cv_dcc.csv":   ("Capacity DCC-CC-CV", 0.01),
}

def load_csv(fname):
    path = os.path.join(DATA_DIR, fname)
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df

# ─────────────────────────────────────────────────────────────
# 5. JALANKAN SIMULASI → KURVA SoC
# ─────────────────────────────────────────────────────────────
def simulate_dataset(fname, soc_true_init, offset=0.0, q00=Q_00, q11=Q_11):
    df = load_csv(fname)
    T  = df["Time(S)"].values
    I  = df["Dir_Cur(A)"].values
    V  = df["Vol(V)"].values

    soc_algo_start = (soc_true_init + offset) if soc_true_init < 0.10 else (soc_true_init - offset)
    soc_true = soc_true_init
    soc_cc   = soc_algo_start
    ekf      = EKFSimulator(soc_algo_start, q00=q00, q11=q11)

    times, trues, ccs, ekfs = [], [], [], []
    time_prev = -1.0
    n = len(T)
    SKIP = max(1, n // 2000)   # downsample for large files

    for idx in range(n):
        t   = T[idx]
        cur = I[idx]
        vol = V[idx]
        dt  = 0.0 if time_prev < 0 else (t - time_prev)
        if time_prev >= 0 and dt <= 0:
            continue
        time_prev = t

        if len(times) == 0:   # first sample — init only
            ekf.x[0] = soc_algo_start
            ekf.x[1] = 0.0
            ekf.P    = np.array([[abs(offset)*50+0.01,0],[0,0.001]])
            times.append(t); trues.append(soc_true); ccs.append(soc_cc); ekfs.append(ekf.x[0])
            continue

        soc_true = np.clip(soc_true - cur*dt/Q_COULOMB, 0, 1)
        ekf.update_rest(cur, dt)
        soc_cc   = np.clip(soc_cc - cur*dt/Q_COULOMB, 0, 1)
        ekf.step(cur, vol, dt)

        if idx % SKIP == 0:
            times.append(t); trues.append(soc_true); ccs.append(soc_cc); ekfs.append(ekf.x[0])

    return np.array(times), np.array(trues), np.array(ccs), np.array(ekfs)

# ─────────────────────────────────────────────────────────────
# 6. RMSE HELPER
# ─────────────────────────────────────────────────────────────
def rmse(a, b):
    return np.sqrt(np.mean((a - b)**2)) * 100  # dalam persen

# ─────────────────────────────────────────────────────────────
# 7. GRAFIK 1 — KURVA SoC RIIL vs CC vs EKF
# ─────────────────────────────────────────────────────────────
def plot_soc_curves():
    # Pilih: Dynamic Profiling (paling representatif) dengan offset 5%
    FNAME   = "dataset_dynamic_profiling_urban_load.csv"
    LABEL   = "Dynamic Profiling Urban Load"
    SOC_INIT = 0.953
    OFFSET   = 0.05

    t, true_, cc_, ekf_ = simulate_dataset(FNAME, SOC_INIT, offset=OFFSET)
    t_h = t / 3600  # detik → jam

    # Hitung RMSE
    r_cc  = rmse(true_, cc_)
    r_ekf = rmse(true_, ekf_)

    fig, axes = plt.subplots(2, 1, figsize=(13, 9),
                             gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0f1117")
    for ax in axes:
        ax.set_facecolor("#161b22")

    ax = axes[0]
    ax.plot(t_h, true_*100, color="#4ade80", lw=2.2, label="SoC Riil (Ground Truth)", zorder=5)
    ax.plot(t_h, cc_  *100, color="#f97316", lw=1.6, ls="--", label=f"SoC Coulomb Counting  (RMSE={r_cc:.2f}%)", zorder=4)
    ax.plot(t_h, ekf_ *100, color="#60a5fa", lw=2.0, label=f"SoC EKF                      (RMSE={r_ekf:.2f}%)", zorder=6)

    ax.set_title(f"Perbandingan SoC Riil vs Estimasi CC vs EKF\nDataset: {LABEL} | Offset Awal: {int(OFFSET*100)}%",
                 color="white", fontsize=13, pad=12)
    ax.set_ylabel("State of Charge (%)", color="white", fontsize=11)
    ax.set_ylim(-2, 105)
    ax.tick_params(colors="white"); ax.spines[:].set_color("#30363d")
    ax.xaxis.label.set_color("white"); ax.yaxis.label.set_color("white")
    ax.legend(facecolor="#21262d", edgecolor="#444", labelcolor="white", fontsize=10)
    ax.grid(True, color="#21262d", lw=0.7)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))

    # Error subplot
    ax2 = axes[1]
    err_cc  = (true_ - cc_)*100
    err_ekf = (true_ - ekf_)*100
    ax2.fill_between(t_h, err_cc,  alpha=0.35, color="#f97316", label="Error CC")
    ax2.fill_between(t_h, err_ekf, alpha=0.45, color="#60a5fa", label="Error EKF")
    ax2.axhline(0, color="#555", lw=0.8, ls="--")
    ax2.set_xlabel("Waktu (jam)", color="white", fontsize=11)
    ax2.set_ylabel("Error (%)", color="white", fontsize=10)
    ax2.legend(facecolor="#21262d", edgecolor="#444", labelcolor="white", fontsize=9)
    ax2.tick_params(colors="white"); ax2.spines[:].set_color("#30363d")
    ax2.grid(True, color="#21262d", lw=0.7)

    plt.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "grafik_soc_comparison.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[OK] Grafik SoC disimpan → {out}")
    return out

# ─────────────────────────────────────────────────────────────
# 8. GRAFIK 2 — GRAFIK BATANG RMSE VARIASI Q & R (tuning)
# ─────────────────────────────────────────────────────────────
def plot_rmse_tuning():
    """
    Data RMSE EKF dari hasil percobaan di Pengujian 1.md, Pengujian 2.md, Pengujian 3.md
    (diambil dari hasil nyata di ESP32, bukan re-simulasi)
    Rata-rata RMSE EKF semua dataset & semua offset per eksperimen.
    """
    # ── Data dari tabel Pengujian 1 ──
    esp13_rmse_ekf = [
        1.3076,1.8255,2.7029,0.7247,1.0811,  # offset 0%
        1.3054,2.0034,5.3392,0.6918,1.0821,  # offset 5%
        1.3017,2.1598,5.0714,33.7356,1.0844  # offset 10%
    ]
    # ── Data dari tabel Pengujian 2 ──
    esp14_rmse_ekf = [
        3.5880,4.0068,5.0441,2.1113,3.2352,  # offset 0%
        3.5868,4.0673,5.6852,2.1114,3.2353,  # offset 5%
        3.5852,4.2170,5.5545,14.6563,3.2350  # offset 10%
    ]
    # ── Data dari tabel Pengujian 3 ──
    esp15_rmse_ekf = [
        1.3427,1.9632,0.7176,0.7452,1.1920,  # offset 0%
        1.3406,2.1350,0.9402,0.7114,1.1929,  # offset 5%
        1.3369,2.2882,1.7563,0.9323,1.1959   # offset 10%
    ]

    # Median RMSE (lebih robust terhadap outlier charging_7.3A divergen)
    def median_exclude_outlier(vals, threshold=10.0):
        filtered = [v for v in vals if v < threshold]
        return np.median(filtered) if filtered else np.median(vals)

    labels = ["Pengujian 1\n(Q₀₀=2e-6,Q₁₁=1e-1\nR_REST=1e-4)",
              "Pengujian 2\n(Q₀₀=1e-5,Q₁₁=5e-2\nR_REST=0.0)",
              "Pengujian 3 ✓\n(Q₀₀=2e-6,Q₁₁=1e-1\nR_REST=1e-4\n+abs(Jacobian))"]
    
    # Hitung rata-rata RMSE per offset group untuk setiap ekperimen
    def group_avg(data):
        g0 = np.mean(data[0:5])
        g5 = np.mean(data[5:10])
        g10 = np.mean([v for v in data[10:15] if v < 15.0])  # exclude diverged
        return g0, g5, g10

    groups_13 = group_avg(esp13_rmse_ekf)
    groups_14 = group_avg(esp14_rmse_ekf)
    groups_15 = group_avg(esp15_rmse_ekf)

    # ── Grafik batang kelompok ──
    x      = np.arange(3)          # 3 kelompok offset
    width  = 0.25
    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#161b22")

    bars13 = ax.bar(x - width, groups_13, width, label="Pengujian 1 (baseline)", color="#f97316", alpha=0.85, edgecolor="#ff6b00")
    bars14 = ax.bar(x,         groups_14, width, label="Pengujian 2 (Q tuning)",  color="#a78bfa", alpha=0.85, edgecolor="#7c5cbf")
    bars15 = ax.bar(x + width, groups_15, width, label="Pengujian 3 ✓ (FINAL)",   color="#4ade80", alpha=0.95, edgecolor="#22c55e")

    # Annotate nilai di atas bar
    for bars in [bars13, bars14, bars15]:
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x()+b.get_width()/2, h+0.08, f"{h:.2f}%",
                    ha="center", va="bottom", color="white", fontsize=8.5, fontweight="bold")

    ax.set_xlabel("Skenario Offset Error Awal SoC", color="white", fontsize=11)
    ax.set_ylabel("Rata-rata RMSE EKF (%)", color="white", fontsize=11)
    ax.set_title("Grafik Batang RMSE EKF pada Variasi Parameter Noise Q dan R\n(Proses Iteratif Tuning: Pengujian 1 → Pengujian 2 → Pengujian 3)",
                 color="white", fontsize=13, pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(["Offset 0%\n(No Init Error)", "Offset 5%\n(Partial Memory Loss)", "Offset 10%\n(Severe Memory Loss)"],
                       color="white", fontsize=10)
    ax.tick_params(colors="white"); ax.spines[:].set_color("#30363d")
    ax.yaxis.label.set_color("white")
    ax.legend(facecolor="#21262d", edgecolor="#444", labelcolor="white", fontsize=10)
    ax.grid(True, axis="y", color="#21262d", lw=0.8)
    ax.set_ylim(0, max(max(groups_13), max(groups_14), max(groups_15)) + 1.5)

    # Anotasi penjelasan
    ax.annotate("Pengujian 2: Q₀₀ dinaikkan 5× → EKF terlalu\npercaya voltage →\nDynamic Profiling naik ke 5%",
                xy=(1, groups_14[0]), xytext=(1.55, groups_14[0]+0.8),
                color="#a78bfa", fontsize=8, arrowprops=dict(arrowstyle="->", color="#a78bfa"))
    ax.annotate("Pengujian 3 fix abs(Jacobian)\n→ divergensi charging\ndihilangkan",
                xy=(2+width, groups_15[2]), xytext=(2.3, groups_15[2]+0.6),
                color="#4ade80", fontsize=8, arrowprops=dict(arrowstyle="->", color="#4ade80"))

    plt.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "grafik_rmse_tuning.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[OK] Grafik RMSE tuning disimpan → {out}")
    return out

# ─────────────────────────────────────────────────────────────
# 9. GRAFIK 3 — SoC ALL DATASETS (multi-panel, offset 0%)
# ─────────────────────────────────────────────────────────────
def plot_all_datasets():
    fnames = list(DATASETS.keys())
    short_labels = [v[0] for v in DATASETS.values()]
    inits        = [v[1] for v in DATASETS.values()]
    OFFSET = 0.0

    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    fig.patch.set_facecolor("#0f1117")
    axes_flat = axes.flatten()

    for i, (fname, label, soc_init) in enumerate(zip(fnames, short_labels, inits)):
        ax = axes_flat[i]
        ax.set_facecolor("#161b22")
        t, true_, cc_, ekf_ = simulate_dataset(fname, soc_init, offset=OFFSET)
        t_h = t / 3600
        r_ekf = rmse(true_, ekf_)
        r_cc  = rmse(true_, cc_)

        ax.plot(t_h, true_*100, color="#4ade80", lw=2.2, label="Riil")
        ax.plot(t_h, cc_  *100, color="#f97316", lw=1.5, ls="--", label=f"CC ({r_cc:.2f}%)")
        ax.plot(t_h, ekf_ *100, color="#60a5fa", lw=2.0, label=f"EKF ({r_ekf:.2f}%)")
        ax.set_title(label, color="white", fontsize=10, pad=6)
        ax.set_ylabel("SoC (%)", color="white", fontsize=9)
        ax.set_xlabel("Waktu (jam)", color="white", fontsize=9)
        ax.tick_params(colors="white"); ax.spines[:].set_color("#30363d")
        ax.legend(facecolor="#21262d", edgecolor="#333", labelcolor="white", fontsize=8)
        ax.grid(True, color="#21262d", lw=0.6)
        ax.set_ylim(-2, 105)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))

    # Sembunyikan subplot ke-6 (kosong)
    axes_flat[5].set_visible(False)

    fig.suptitle("Perbandingan SoC Riil vs CC vs EKF — Semua Dataset (Offset 0%)\nParameter: Pengujian 3 Final",
                 color="white", fontsize=13, y=1.01)
    plt.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "grafik_soc_all_datasets.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[OK] Grafik multi-dataset disimpan → {out}")
    return out

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  VISUALISASI SoC — PIL ESP32 (Pengujian 3 final parameter)")
    print("=" * 60)
    try:
        import matplotlib
        matplotlib.rcParams.update({
            "font.family": "DejaVu Sans",
            "axes.unicode_minus": False,
        })
    except Exception:
        pass

    plot_soc_curves()
    plot_rmse_tuning()
    plot_all_datasets()
    print("\n[DONE] Semua grafik berhasil dibuat.")
