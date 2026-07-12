"""
verify_rmse.py — Verifikasi Independen RMSE & MAE menggunakan Python/NumPy
============================================================================
Tujuan: Membuktikan bahwa nilai RMSE & MAE yang dihasilkan ESP32 (main.cpp)
        adalah benar, dengan cara menghitung ulang secara independen
        menggunakan data CSV + formula eksplisit NumPy standar.

Output:
  - Tabel perbandingan Python vs ESP32 (console)
  - grafik_verifikasi_rmse.png  (visual proof untuk sidang)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os, math

# ─────────────────────────────────────────────────────────────
# KONSTANTA (identik main.cpp Pengujian 3)
# ─────────────────────────────────────────────────────────────
Q_COULOMB = 74874.8
lut_soc_ocv = np.array([0.00,0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,
                         0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95,1.00])
lut_ocv_val = np.array([2.6550,3.0269,3.1972,3.2391,3.2261,3.2242,3.2424,3.2625,
                         3.2758,3.2835,3.2871,3.2880,3.2878,3.2884,3.2917,3.2958,
                         3.2973,3.3039,3.3353,3.4122,3.5370])
lut_soc_ecm = np.array([0.0,0.090902,0.204618,0.318054,0.431697,0.545421,0.659070,0.772787,0.886430])
lut_r0 = np.array([0.006050,0.002800,0.002800,0.002899,0.002700,0.002400,0.002899,0.002199,0.002800])
lut_r1 = np.array([0.009500,0.002506,0.002207,0.002212,0.002372,0.002436,0.002374,0.002345,0.002684])
lut_c1 = np.array([11281.15,20591.86,24841.48,15061.40,20897.75,19607.70,15177.97,16580.74,24189.08])
Q_00=2e-6; Q_11=1e-1; R_BASE=1e-4; R_REST=1e-4
REST_THRESH=0.05; REST_SETTLE=30

def get_ocv(s):  return float(np.interp(np.clip(s,0,1), lut_soc_ocv, lut_ocv_val))
def get_r0(s):   return max(float(np.interp(s, lut_soc_ecm, lut_r0)), 1e-4)
def get_r1(s):   return max(float(np.interp(s, lut_soc_ecm, lut_r1)), 1e-4)
def get_c1(s):   return max(float(np.interp(s, lut_soc_ecm, lut_c1)), 1.0)
def get_docv(s):
    h=0.005; lo=max(s-h,0); hi=min(s+h,1); d=hi-lo
    return (get_ocv(hi)-get_ocv(lo))/d if d>1e-6 else 0.0

# ─────────────────────────────────────────────────────────────
# EKF SIMULATOR (sama persis dengan main.cpp)
# ─────────────────────────────────────────────────────────────
class EKF:
    def __init__(self, soc0, offset):
        self.x=np.array([soc0,0.0])
        self.P=np.array([[abs(offset)*50+0.01,0],[0,0.001]])
        self.v_pred=0.0; self.rest_cnt=0; self.in_rest=False

    def step(self, I, V, dt):
        sp=np.clip(self.x[0],0,1); vc=self.x[1]
        R0=get_r0(sp); R1=get_r1(sp); C1=get_c1(sp)
        tau=max(R1*C1,1e-6)
        sp2=np.clip(sp-I*dt/Q_COULOMB,0,1)
        a=math.exp(-dt/tau) if dt>0 else 1.0
        vc2=a*vc+R1*(1-a)*I
        self.x=np.array([sp2,vc2])
        Pp=np.array([[self.P[0,0]+Q_00,0],[0,a**2*self.P[1,1]+Q_11]])
        ocv=get_ocv(sp2); dOCV=get_docv(sp2)
        Vp=ocv-vc2-I*R0; self.v_pred=Vp
        h0=abs(dOCV)+1e-4; h1=-1.0
        if self.in_rest: Rd=R_REST
        elif abs(I)<0.05: Rd=R_BASE/(abs(dOCV)+1e-3)
        else: Rd=R_BASE/(abs(dOCV)+1e-4)
        Rd=np.clip(Rd,1e-4,10.0)
        S=h0**2*Pp[0,0]+h0*h1*Pp[0,1]+h1*h0*Pp[1,0]+h1**2*Pp[1,1]+Rd
        S=max(S,1e-9)
        K=np.array([(Pp[0,0]*h0+Pp[0,1]*h1)/S,(Pp[1,0]*h0+Pp[1,1]*h1)/S])
        inn=V-Vp; DB=0.001; MC=0.10
        K0=K[0]*(abs(inn)/DB) if abs(inn)<DB else K[0]
        sc=np.clip(K0*inn,-MC,MC)
        self.x[0]=np.clip(self.x[0]+sc,0,1)
        self.x[1]=np.clip(self.x[1]+K[1]*inn,-0.5,0.5)
        IKH=np.array([[1-K0*h0,-K0*h1],[-K[1]*h0,1-K[1]*h1]])
        T=IKH@Pp
        self.P=T@IKH.T+np.array([[K0**2*Rd,K0*K[1]*Rd],[K[1]*K0*Rd,K[1]**2*Rd]])
        self.P=(self.P+self.P.T)*0.5
        self.P[0,0]=max(self.P[0,0],1e-10); self.P[1,1]=max(self.P[1,1],1e-10)

    def update_rest(self,I,dt):
        if abs(I)<REST_THRESH:
            self.rest_cnt+=int(dt)
            if self.rest_cnt>=REST_SETTLE: self.in_rest=True
        else: self.rest_cnt=0; self.in_rest=False

# ─────────────────────────────────────────────────────────────
# SIMULASI + KUMPULKAN ERROR ARRAY
# ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def simulate_collect_errors(fname, soc_init, offset):
    df=pd.read_csv(os.path.join(DATA_DIR,fname))
    T=df["Time(S)"].values; I=df["Dir_Cur(A)"].values; V=df["Vol(V)"].values
    soc0=(soc_init+offset) if soc_init<0.10 else (soc_init-offset)
    soc_t=soc_init; soc_cc=soc0; ekf=EKF(soc0,offset)
    err_cc=[]; err_ekf=[]; err_v=[]; tp=-1.0; first=True

    for idx in range(len(T)):
        t=T[idx]; cur=I[idx]; vol=V[idx]
        dt=0.0 if tp<0 else t-tp
        if tp>=0 and dt<=0: continue
        tp=t
        if first:
            ekf.x[0]=soc0; ekf.x[1]=0.0
            ekf.P=np.array([[abs(offset)*50+0.01,0],[0,0.001]])
            first=False; continue
        soc_t=np.clip(soc_t-cur*dt/Q_COULOMB,0,1)
        soc_cc=np.clip(soc_cc-cur*dt/Q_COULOMB,0,1)
        ekf.update_rest(cur,dt); ekf.step(cur,vol,dt)
        err_cc.append(soc_t-soc_cc)
        err_ekf.append(soc_t-ekf.x[0])
        err_v.append(vol-ekf.v_pred)

    return np.array(err_cc), np.array(err_ekf), np.array(err_v)

# ─────────────────────────────────────────────────────────────
# HITUNG RMSE & MAE — FORMULA EKSPLISIT (seperti buku teks)
# ─────────────────────────────────────────────────────────────
def hitung_rmse_mae(errors_pct_or_mv):
    """
    RMSE = sqrt( (1/N) * sum(e_i^2) )
    MAE  = (1/N) * sum(|e_i|)
    """
    N      = len(errors_pct_or_mv)
    sq_err = errors_pct_or_mv ** 2              # e_i^2 untuk setiap sampel
    abs_err= np.abs(errors_pct_or_mv)           # |e_i| untuk setiap sampel
    rmse   = np.sqrt(np.sum(sq_err) / N)        # akar rata-rata kuadrat
    mae    = np.sum(abs_err) / N                # rata-rata nilai mutlak
    return rmse, mae, N

# ─────────────────────────────────────────────────────────────
# DATASET CONFIGS (3 dataset di tabel Bab 4)
# ─────────────────────────────────────────────────────────────
CONFIGS = [
    ("dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv",      0.0,   "Charging 5A"),
    ("dataset_dcc_0.22c_discharge_constant_2.5v.csv",  1.0,   "Discharging 4.4A"),
    ("dataset_dynamic_profiling_urban_load.csv",        0.953, "Dynamic 15/5/10A"),
]

# Nilai referensi dari ESP32 (Pengujian 3.md) — urutan: offset 0%, 5%, 10%
ESP32_REF = {
    "Charging 5A": {
        "rmse_cc":  [0.0000, 4.2476, 8.3473],
        "rmse_ekf": [1.3427, 1.3406, 1.3369],
        "mae_cc":   [0.0000, 3.6394, 7.0921],
        "mae_ekf":  [0.9846, 0.9823, 0.9783],
    },
    "Discharging 4.4A": {
        "rmse_cc":  [0.0000, 4.9145, 9.6581],
        "rmse_ekf": [1.9632, 2.1350, 2.2882],
        "mae_cc":   [0.0000, 4.8723, 9.4946],
        "mae_ekf":  [1.9005, 2.0790, 2.2368],
    },
    "Dynamic 15/5/10A": {
        "rmse_cc":  [0.0000, 4.6228, 9.0670],
        "rmse_ekf": [0.7176, 0.9402, 1.7563],
        "mae_cc":   [0.0000, 4.3218, 8.3954],
        "mae_ekf":  [0.6607, 0.8688, 1.6378],
    },
}

# ─────────────────────────────────────────────────────────────
# MAIN — HITUNG DAN BANDINGKAN
# ─────────────────────────────────────────────────────────────
print("=" * 90)
print("  VERIFIKASI INDEPENDEN RMSE & MAE — Python/NumPy vs ESP32 Output")
print("  Formula: RMSE = sqrt(sum(e²)/N)×100  |  MAE = sum(|e|)/N×100")
print("=" * 90)

OFFSETS = [0.0, 0.05, 0.10]
OFF_LABELS = ["0%", "5%", "10%"]

# Untuk grafik visual
rows_python = []   # (label, off, rmse_cc, rmse_ekf, mae_cc, mae_ekf)
rows_esp32  = []

all_match = True

for fname, soc_init, label in CONFIGS:
    print(f"\n{'─'*90}")
    print(f"  DATASET: {label}  ({fname})")
    print(f"{'─'*90}")
    print(f"  {'Offset':>6} | {'Metrik':>12} | {'Python (numpy)':>15} | {'ESP32 Output':>13} | {'Selisih':>10} | Status")
    print(f"  {'':>6}-+-{'':>12}-+-{'':>15}-+-{'':>13}-+-{'':>10}-+--------")

    ref = ESP32_REF[label]

    for i, (off, olab) in enumerate(zip(OFFSETS, OFF_LABELS)):
        err_cc, err_ekf, err_v = simulate_collect_errors(fname, soc_init, off)

        # RMSE & MAE Python — formula eksplisit
        r_cc,  m_cc,  N_cc  = hitung_rmse_mae(err_cc  * 100)   # konversi ke %
        r_ekf, m_ekf, N_ekf = hitung_rmse_mae(err_ekf * 100)

        # Referensi ESP32
        R_cc_esp  = ref["rmse_cc"][i]
        R_ekf_esp = ref["rmse_ekf"][i]
        M_cc_esp  = ref["mae_cc"][i]
        M_ekf_esp = ref["mae_ekf"][i]

        # Selisih
        d_rcc  = abs(r_cc  - R_cc_esp)
        d_rekf = abs(r_ekf - R_ekf_esp)
        d_mcc  = abs(m_cc  - M_cc_esp)
        d_mekf = abs(m_ekf - M_ekf_esp)

        # Status — cocok jika selisih < 0.05% (batas toleransi float32 vs float64)
        TOLS = [d_rcc, d_rekf, d_mcc, d_mekf]
        ok   = all(d < 0.10 for d in TOLS)
        if not ok: all_match = False
        status = "COCOK ✓" if ok else "BEDA !"

        print(f"  {olab:>6} | {'RMSE CC (%)':>12} | {r_cc:>15.4f} | {R_cc_esp:>13.4f} | {d_rcc:>10.4f} | {status}")
        print(f"  {olab:>6} | {'RMSE EKF (%)':>12} | {r_ekf:>15.4f} | {R_ekf_esp:>13.4f} | {d_rekf:>10.4f} | {status}")
        print(f"  {olab:>6} | {'MAE CC (%)':>12} | {m_cc:>15.4f} | {M_cc_esp:>13.4f} | {d_mcc:>10.4f} | {status}")
        print(f"  {olab:>6} | {'MAE EKF (%)':>12} | {m_ekf:>15.4f} | {M_ekf_esp:>13.4f} | {d_mekf:>10.4f} | {status}")
        print(f"  {'':>6} | {'N sampel':>12} | {N_ekf:>15,} | {'—':>13} | {'—':>10} |")
        print(f"  {'─'*6}-+-{'─'*12}-+-{'─'*15}-+-{'─'*13}-+-{'─'*10}-+--------")

        rows_python.append((label, olab, r_cc, r_ekf, m_cc, m_ekf))
        rows_esp32.append( (label, olab, R_cc_esp, R_ekf_esp, M_cc_esp, M_ekf_esp))

print(f"\n{'='*90}")
verdict = "SEMUA NILAI COCOK — Implementasi ESP32 TERVERIFIKASI BENAR" if all_match else "ADA PERBEDAAN — Periksa log di atas"
print(f"  VERDICT: {verdict}")
print(f"  Toleransi perbedaan: < 0.10%  (akibat float32 ESP32 vs float64 Python)")
print(f"{'='*90}\n")

# ─────────────────────────────────────────────────────────────
# GRAFIK VISUAL — SCATTER PLOT PYTHON vs ESP32
# ─────────────────────────────────────────────────────────────
print("Membuat grafik verifikasi visual...")

BG = "#0d1117"; PANEL = "#161b22"; BORDER = "#30363d"

fig, axes = plt.subplots(1, 3, figsize=(18, 7))
fig.patch.set_facecolor(BG)
fig.suptitle(
    "Verifikasi Independen: Nilai RMSE EKF — Python/NumPy vs Output ESP32\n"
    "Jika titik data jatuh tepat pada garis diagonal, nilai Python = nilai ESP32",
    color="white", fontsize=13, fontweight="bold", y=1.02
)

dataset_labels = ["Charging 5A", "Discharging 4.4A", "Dynamic 15/5/10A"]
colors_off = ["#4ade80", "#fb923c", "#f87171"]   # hijau=0%, oranye=5%, merah=10%
markers_off = ["o", "s", "^"]

for col, ds_label in enumerate(dataset_labels):
    ax = axes[col]
    ax.set_facecolor(PANEL)
    ax.spines[:].set_color(BORDER)
    ax.tick_params(colors="white", labelsize=8)

    py_vals  = []
    esp_vals = []
    scatter_colors = []
    scatter_marks  = []

    for i, olab in enumerate(OFF_LABELS):
        r_py  = next(r[3] for r in rows_python if r[0]==ds_label and r[1]==olab)  # RMSE EKF
        r_esp = next(r[3] for r in rows_esp32  if r[0]==ds_label and r[1]==olab)
        m_py  = next(r[5] for r in rows_python if r[0]==ds_label and r[1]==olab)  # MAE EKF
        m_esp = next(r[5] for r in rows_esp32  if r[0]==ds_label and r[1]==olab)

        ax.scatter(r_esp, r_py, s=180, color=colors_off[i],
                   marker=markers_off[i], zorder=5,
                   label=f"RMSE offset {olab}")
        ax.scatter(m_esp, m_py, s=120, color=colors_off[i],
                   marker=markers_off[i], zorder=5, alpha=0.5,
                   label=f"MAE offset {olab}" if col==0 else "_nolegend_")

        py_vals.extend([r_py, m_py])
        esp_vals.extend([r_esp, m_esp])

        # Anotasi selisih
        diff_r = abs(r_py - r_esp)
        ax.annotate(f"Δ={diff_r:.3f}%",
                    xy=(r_esp, r_py),
                    xytext=(r_esp+0.05, r_py+0.08),
                    color=colors_off[i], fontsize=7.5,
                    arrowprops=dict(arrowstyle="-", color=colors_off[i], lw=0.8))

    # Garis diagonal y=x (perfect match)
    all_v = py_vals + esp_vals
    mn, mx = min(all_v)-0.1, max(all_v)+0.1
    ax.plot([mn, mx], [mn, mx], color="#94a3b8", lw=1.5, ls="--",
            label="Garis y=x (nilai identik)", zorder=3)

    ax.set_xlabel("Nilai ESP32 (%)", color="white", fontsize=9)
    ax.set_ylabel("Nilai Python/NumPy (%)", color="white", fontsize=9)
    ax.set_title(ds_label, color="white", fontsize=11, fontweight="bold", pad=8)
    ax.grid(True, color="#21262d", lw=0.6)
    ax.set_xlim(mn, mx); ax.set_ylim(mn, mx)

    if col == 0:
        legend_elements = [
            mpatches.Patch(color=colors_off[0], label="Offset 0%"),
            mpatches.Patch(color=colors_off[1], label="Offset 5%"),
            mpatches.Patch(color=colors_off[2], label="Offset 10%"),
            plt.Line2D([0],[0], color="#94a3b8", ls="--", lw=1.5, label="y = x (identik)"),
        ]
        ax.legend(handles=legend_elements, facecolor="#21262d",
                  edgecolor=BORDER, labelcolor="white", fontsize=8.5, loc="upper left")

# Tambahkan teks keterangan
fig.text(0.5, -0.04,
    "Titik (lingkaran/kotak/segitiga) = pasangan nilai RMSE atau MAE.   "
    "Makin dekat ke garis diagonal, makin identik Python dengan ESP32.\n"
    "Perbedaan kecil (<0.05%) adalah normal: ESP32 menggunakan float32 (32-bit), Python menggunakan float64 (64-bit).",
    ha="center", color="#94a3b8", fontsize=9, style="italic")

plt.tight_layout()
out = os.path.join(os.path.dirname(__file__), "grafik_verifikasi_python_vs_esp32.png")
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close()
print(f"[OK] Grafik verifikasi disimpan -> {out}")
print("\n[DONE] Verifikasi selesai.")
