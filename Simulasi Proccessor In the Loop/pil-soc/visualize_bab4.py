"""
visualize_bab4.py — Grafik khusus untuk Bab 4 Skripsi
Menghasilkan grafik yang persis sesuai tabel di slide bab4:
  - Dataset 1: Constant Charging 5A     (dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv)
  - Dataset 2: Constant Discharging 4.4A (dataset_dcc_0.22c_discharge_constant_2.5v.csv)
  - Dataset 3: Discharging 15A,5A,10A   (dataset_dynamic_profiling_urban_load.csv)

Output:
  grafik_bab4_charging5a.png
  grafik_bab4_discharging44a.png
  grafik_bab4_dynamic.png
  grafik_bab4_rmse_tuning.png      <- untuk menjawab pertanyaan soal pemilihan Q,R
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os, math

# ─────────────────────────────────────────────────────────────
# 1. KONSTANTA MODEL (identik dengan main.cpp Pengujian 3)
# ─────────────────────────────────────────────────────────────
Q_COULOMB = 74874.8

lut_soc_ocv = np.array([0.00,0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,
                         0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95,1.00])
lut_ocv_val = np.array([2.6550,3.0269,3.1972,3.2391,3.2261,3.2242,3.2424,3.2625,
                         3.2758,3.2835,3.2871,3.2880,3.2878,3.2884,3.2917,3.2958,
                         3.2973,3.3039,3.3353,3.4122,3.5370])
lut_soc_ecm = np.array([0.0,0.090902,0.204618,0.318054,0.431697,0.545421,0.659070,0.772787,0.886430])
lut_r0      = np.array([0.006050,0.002800,0.002800,0.002899,0.002700,0.002400,0.002899,0.002199,0.002800])
lut_r1      = np.array([0.009500,0.002506,0.002207,0.002212,0.002372,0.002436,0.002374,0.002345,0.002684])
lut_c1      = np.array([11281.15,20591.86,24841.48,15061.40,20897.75,19607.70,15177.97,16580.74,24189.08])

Q_00=2e-6; Q_11=1e-1; R_BASE=1e-4; R_REST=1e-4
REST_THRESH=0.05; REST_SETTLE=30

# ─────────────────────────────────────────────────────────────
# 2. HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def get_ocv(s):    return float(np.interp(np.clip(s,0,1), lut_soc_ocv, lut_ocv_val))
def get_r0(s):     return max(float(np.interp(s, lut_soc_ecm, lut_r0)), 1e-4)
def get_r1(s):     return max(float(np.interp(s, lut_soc_ecm, lut_r1)), 1e-4)
def get_c1(s):     return max(float(np.interp(s, lut_soc_ecm, lut_c1)), 1.0)
def get_docv(s):
    h=0.005; lo=max(s-h,0); hi=min(s+h,1); d=hi-lo
    return (get_ocv(hi)-get_ocv(lo))/d if d>1e-6 else 0.0

# ─────────────────────────────────────────────────────────────
# 3. EKF SIMULATOR
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
# 4. SIMULASI
# ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def simulate(fname, soc_init, offset):
    df=pd.read_csv(os.path.join(DATA_DIR,fname))
    T=df["Time(S)"].values; I=df["Dir_Cur(A)"].values; V=df["Vol(V)"].values
    soc0=(soc_init+offset) if soc_init<0.10 else (soc_init-offset)
    soc_t=soc_init; soc_cc=soc0; ekf=EKF(soc0,offset)
    ts,trues,ccs,ekfs=[],[],[],[]
    tp=-1.0; n=len(T)
    SKIP=max(1,n//3000)
    for idx in range(n):
        t=T[idx]; cur=I[idx]; vol=V[idx]
        dt=0.0 if tp<0 else t-tp
        if tp>=0 and dt<=0: continue
        tp=t
        if not ts:
            ekf.x[0]=soc0; ekf.x[1]=0.0
            ekf.P=np.array([[abs(offset)*50+0.01,0],[0,0.001]])
            ts.append(t); trues.append(soc_t); ccs.append(soc_cc); ekfs.append(ekf.x[0])
            continue
        soc_t=np.clip(soc_t-cur*dt/Q_COULOMB,0,1)
        soc_cc=np.clip(soc_cc-cur*dt/Q_COULOMB,0,1)
        ekf.update_rest(cur,dt); ekf.step(cur,vol,dt)
        if idx%SKIP==0:
            ts.append(t); trues.append(soc_t); ccs.append(soc_cc); ekfs.append(ekf.x[0])
    return np.array(ts),np.array(trues),np.array(ccs),np.array(ekfs)

def rmse(a,b): return np.sqrt(np.mean((a-b)**2))*100

# ─────────────────────────────────────────────────────────────
# 5. STYLE HELPER
# ─────────────────────────────────────────────────────────────
BG_DARK  = "#0d1117"
BG_PANEL = "#161b22"
BORDER   = "#30363d"
COL_REAL = "#4ade80"
COL_CC   = "#fb923c"
COL_EKF  = "#38bdf8"
COL_ERR_CC  = "#fb923c"
COL_ERR_EKF = "#38bdf8"

def style_ax(ax):
    ax.set_facecolor(BG_PANEL)
    ax.tick_params(colors="white", labelsize=8)
    ax.spines[:].set_color(BORDER)
    ax.yaxis.label.set_color("white"); ax.xaxis.label.set_color("white")
    ax.grid(True, color="#21262d", lw=0.6, zorder=0)

# ─────────────────────────────────────────────────────────────
# 6. GRAFIK PER DATASET — 3 PANEL OFFSET (0%, 5%, 10%)
# ─────────────────────────────────────────────────────────────
def plot_dataset_3offset(fname, soc_init, dataset_label, outfile):
    offsets    = [0.0, 0.05, 0.10]
    off_labels = ["Offset 0%  (No Init Error)",
                  "Offset 5%  (Memory Loss Parsial)",
                  "Offset 10% (Memory Loss Besar)"]

    # Ambil data dari Pengujian 3.md yang relevan
    # (kecocokan dengan tabel di slide bab4)
    esp15_rmse_cc  = {0.0:0.0, 0.05:None, 0.10:None}
    esp15_rmse_ekf = {0.0:None, 0.05:None, 0.10:None}

    fig, axes = plt.subplots(3, 1, figsize=(13, 13), sharex=False)
    fig.patch.set_facecolor(BG_DARK)
    fig.suptitle(f"Perbandingan SoC Riil vs CC vs EKF\nDataset: {dataset_label}  |  Parameter EKF: Pengujian 3 (Final)",
                 color="white", fontsize=13, y=0.98, fontweight="bold")

    for i, (off, olab) in enumerate(zip(offsets, off_labels)):
        t, true_, cc_, ekf_ = simulate(fname, soc_init, off)
        t_h = t/3600
        r_cc  = rmse(true_, cc_)
        r_ekf = rmse(true_, ekf_)

        ax = axes[i]
        style_ax(ax)
        ax.plot(t_h, true_*100, color=COL_REAL, lw=2.2, label="SoC Riil (Ground Truth)", zorder=5)
        ax.plot(t_h, cc_  *100, color=COL_CC,   lw=1.8, ls="--",
                label=f"SoC Coulomb Counting  RMSE = {r_cc:.4f}%", zorder=4)
        ax.plot(t_h, ekf_ *100, color=COL_EKF,  lw=2.2,
                label=f"SoC EKF (Pengujian 3)           RMSE = {r_ekf:.4f}%", zorder=6)
        ax.set_ylim(-3, 108)
        ax.set_ylabel("SoC (%)", color="white", fontsize=9)
        ax.set_title(f"Skenario {olab}", color="#94a3b8", fontsize=10, pad=5)
        ax.legend(facecolor="#21262d", edgecolor=BORDER, labelcolor="white",
                  fontsize=9, loc="upper right")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f"{x:.0f}%"))

    axes[-1].set_xlabel("Waktu (jam)", color="white", fontsize=10)
    plt.tight_layout(rect=[0,0,1,0.96])
    out = os.path.join(os.path.dirname(__file__), outfile)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    plt.close()
    print(f"[OK] {outfile}")
    return out

# ─────────────────────────────────────────────────────────────
# 7. GRAFIK BATANG RMSE TUNING — Khusus untuk Pertanyaan2
#    Memvisualisasikan mengapa Pengujian 3 dipilih
# ─────────────────────────────────────────────────────────────
def plot_rmse_tuning_per_dataset():
    """
    Grafik batang RMSE EKF per dataset, per iterasi (Pengujian 1, Pengujian 2, Pengujian 3)
    Nilai diambil langsung dari .md file (hasil nyata ESP32)
    """
    datasets_short = ["Charging 5A", "Discharging 4.4A", "Dynamic 15/5/10A"]

    # Nilai RMSE EKF offset 0% dari masing-masing esp (3 dataset utama bab4)
    # Urutan: [Charging5A, Discharging4.4A, Dynamic]
    data_esp13_0  = [1.3076, 1.8255, 2.7029]
    data_esp14_0  = [3.5880, 4.0068, 5.0441]
    data_esp15_0  = [1.3427, 1.9632, 0.7176]

    data_esp13_5  = [1.3054, 2.0034, 5.3392]
    data_esp14_5  = [3.5868, 4.0673, 5.6852]
    data_esp15_5  = [1.3406, 2.1350, 0.9402]

    data_esp13_10 = [1.3017, 2.1598, 5.0714]
    data_esp14_10 = [3.5852, 4.2170, 5.5545]
    data_esp15_10 = [1.3369, 2.2882, 1.7563]

    offsets = ["Offset 0%", "Offset 5%", "Offset 10%"]
    all_esp13 = [data_esp13_0, data_esp13_5, data_esp13_10]
    all_esp14 = [data_esp14_0, data_esp14_5, data_esp14_10]
    all_esp15 = [data_esp15_0, data_esp15_5, data_esp15_10]

    fig, axes = plt.subplots(1, 3, figsize=(17, 7), sharey=False)
    fig.patch.set_facecolor(BG_DARK)
    fig.suptitle("Grafik Batang RMSE EKF — Perbandingan Iterasi Tuning Parameter Q & R\n"
                 "Proses Seleksi: Pengujian 1 (baseline) → Pengujian 2 (Q tuning) → Pengujian 3 ✓ (FINAL)",
                 color="white", fontsize=13, y=1.01, fontweight="bold")

    x = np.arange(len(datasets_short))
    w = 0.25

    for col, (offset_label, e13, e14, e15) in enumerate(zip(offsets, all_esp13, all_esp14, all_esp15)):
        ax = axes[col]
        ax.set_facecolor(BG_PANEL)

        b13 = ax.bar(x-w,   e13, w, label="Pengujian 1 (baseline)", color="#f97316", alpha=0.85, edgecolor="#c2410c")
        b14 = ax.bar(x,     e14, w, label="Pengujian 2 (Q naik 5x)", color="#a855f7", alpha=0.85, edgecolor="#7e22ce")
        b15 = ax.bar(x+w,   e15, w, label="Pengujian 3 ✓ FINAL",    color="#22c55e", alpha=0.95, edgecolor="#15803d")

        for bars in [b13, b14, b15]:
            for b in bars:
                h = b.get_height()
                ax.text(b.get_x()+b.get_width()/2, h+0.06, f"{h:.2f}%",
                        ha="center", va="bottom", color="white", fontsize=7.5, fontweight="bold")

        ax.set_title(offset_label, color="#94a3b8", fontsize=11, pad=8)
        ax.set_xticks(x)
        ax.set_xticklabels(datasets_short, color="white", fontsize=8.5, rotation=8)
        ax.set_ylabel("RMSE EKF (%)", color="white", fontsize=9)
        ax.tick_params(colors="white")
        ax.spines[:].set_color(BORDER)
        ax.grid(True, axis="y", color="#21262d", lw=0.8)
        ax.set_ylim(0, max(max(e13),max(e14),max(e15))*1.3 + 0.5)
        if col == 0:
            ax.legend(facecolor="#21262d", edgecolor=BORDER, labelcolor="white",
                      fontsize=8, loc="upper right")

    # Tambahkan catatan penting
    fig.text(0.5, -0.03,
             "Catatan: Pengujian 2 menaikkan Q₀₀ dari 2e-6 ke 1e-5 → EKF over-trust measurement → RMSE memburuk.\n"
             "Pengujian 3 fix kritis: revert Q₀₀ + fabsf(Jacobian) → eliminasi divergensi charging 7.3A + Dynamic Profiling membaik drastis.",
             ha="center", color="#94a3b8", fontsize=9, style="italic")

    plt.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "grafik_bab4_rmse_tuning.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    plt.close()
    print(f"[OK] grafik_bab4_rmse_tuning.png")
    return out

# ─────────────────────────────────────────────────────────────
# 8. GRAFIK RINGKASAN — 3×3 grid: 3 offset × 3 dataset
# ─────────────────────────────────────────────────────────────
def plot_summary_all_offsets():
    configs = [
        ("dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv",       0.0,   "Charging 5A"),
        ("dataset_dcc_0.22c_discharge_constant_2.5v.csv",   1.0,   "Discharging 4.4A"),
        ("dataset_dynamic_profiling_urban_load.csv",         0.953, "Dynamic 15A/5A/10A"),
    ]
    offsets     = [0.0, 0.05, 0.10]
    off_labels  = ["Offset 0%", "Offset 5%", "Offset 10%"]

    fig, axes = plt.subplots(3, 3, figsize=(18, 14))
    fig.patch.set_facecolor(BG_DARK)
    fig.suptitle("Perbandingan SoC Riil vs Coulomb Counting vs EKF",
                 color="white", fontsize=14, fontweight="bold", y=0.995)

    for row, (off, olab) in enumerate(zip(offsets, off_labels)):
        for col, (fname, soc_init, ds_label) in enumerate(configs):
            t, true_, cc_, ekf_ = simulate(fname, soc_init, off)
            t_h  = t / 3600
            r_cc  = rmse(true_, cc_)
            r_ekf = rmse(true_, ekf_)

            ax = axes[row][col]
            style_ax(ax)

            ax.plot(t_h, true_*100, color=COL_REAL, lw=2.2, label="SoC Riil", zorder=5)
            ax.plot(t_h, cc_  *100, color=COL_CC,   lw=1.6, ls="--",
                    label=f"CC   RMSE={r_cc:.4f}%",  zorder=4)
            ax.plot(t_h, ekf_ *100, color=COL_EKF,  lw=2.0,
                    label=f"EKF  RMSE={r_ekf:.4f}%", zorder=6)

            ax.set_ylim(-3, 108)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
            ax.legend(facecolor="#21262d", edgecolor=BORDER, labelcolor="white",
                      fontsize=7.8, loc="upper right")
            ax.set_xlabel("Waktu (jam)", color="white", fontsize=8)

            # Kolom paling kiri: label offset sebagai ylabel
            if col == 0:
                ax.set_ylabel(f"{olab}\nSoC (%)", color="#94a3b8",
                              fontsize=9, fontweight="bold")
            else:
                ax.set_ylabel("SoC (%)", color="white", fontsize=8)

            # Baris paling atas: label nama dataset sebagai title
            if row == 0:
                ax.set_title(ds_label, color="white", fontsize=11,
                             fontweight="bold", pad=7)

    plt.tight_layout(rect=[0, 0, 1, 0.993])
    out = os.path.join(os.path.dirname(__file__), "grafik_bab4_summary.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    plt.close()
    print(f"[OK] grafik_bab4_summary.png")
    return out

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import matplotlib; matplotlib.rcParams.update({"axes.unicode_minus":False})

    print("Generating charts for Bab 4...")

    # Grafik per-dataset (3 panel offset)
    plot_dataset_3offset(
        "dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv", 0.0,
        "Constant Charging 5A", "grafik_bab4_charging5a.png")

    plot_dataset_3offset(
        "dataset_dcc_0.22c_discharge_constant_2.5v.csv", 1.0,
        "Constant Discharging 4.4A", "grafik_bab4_discharging44a.png")

    plot_dataset_3offset(
        "dataset_dynamic_profiling_urban_load.csv", 0.953,
        "Discharging 15A, 5A, 10A (Dynamic Profiling)", "grafik_bab4_dynamic.png")

    # Grafik batang RMSE tuning
    plot_rmse_tuning_per_dataset()

    # Grafik ringkasan 3×3 (semua offset)
    plot_summary_all_offsets()

    print("\n[DONE] Semua grafik Bab 4 selesai.")
