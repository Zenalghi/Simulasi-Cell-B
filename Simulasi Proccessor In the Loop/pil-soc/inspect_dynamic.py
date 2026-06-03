import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path('data')

# --- Inspeksi dataset Dynamic Profiling ---
fname = 'clean_h-Dynamic_Profiling_(Urban Load).csv'
df = pd.read_csv(DATA_DIR / fname)

print('=== INSPEKSI DATASET Dynamic Profiling ===')
print(f'Total rows: {len(df)}')
print(f'Columns: {list(df.columns)}')
t0 = df['Time(S)'].iloc[0]
t1 = df['Time(S)'].iloc[-1]
print(f'Time range: {t0:.1f} - {t1:.1f} s  ({(t1-t0)/3600:.2f} jam)')
print(f'dt rata-rata: {(t1-t0)/(len(df)-1):.2f} s')
print()
print('--- 15 Baris Pertama ---')
print(df[['Time(S)', 'Dir_Cur(A)', 'Vol(V)']].head(15).to_string())
print()
print('--- Statistik Current ---')
print(df['Dir_Cur(A)'].describe())
print()

# Hitung SoC trace tanpa EKF
Q = 74874.8
soc_true = 1.0
t_prev = -1.0
print('--- SoC true trace awal (20 sampel pertama) dengan EKF trace di offset 5% ---')
soc_ekf = 0.95

lut_soc_ocv = [0.00,0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95,1.00]
lut_ocv_val = [2.6550,3.0269,3.1972,3.2391,3.2261,3.2242,3.2424,3.2625,3.2758,3.2835,3.2871,3.2880,3.2878,3.2884,3.2917,3.2958,3.2973,3.3039,3.3353,3.4122,3.5370]

def OCV_lut(s):
    s = max(0.0, min(1.0, s))
    for i in range(len(lut_soc_ocv)-1):
        if lut_soc_ocv[i] <= s <= lut_soc_ocv[i+1]:
            t = (s-lut_soc_ocv[i])/(lut_soc_ocv[i+1]-lut_soc_ocv[i])
            return lut_ocv_val[i] + t*(lut_ocv_val[i+1]-lut_ocv_val[i])
    return lut_ocv_val[-1]

for i in range(min(25, len(df))):
    t = df['Time(S)'].iloc[i]
    I = df['Dir_Cur(A)'].iloc[i]
    V = df['Vol(V)'].iloc[i]
    dt = 0 if t_prev < 0 else t - t_prev
    t_prev = t
    if dt > 0:
        soc_true = max(0, min(1, soc_true - I*dt/Q))
        soc_ekf  = max(0, min(1, soc_ekf  - I*dt/Q))
    V_pred_true = OCV_lut(soc_true)
    V_pred_ekf  = OCV_lut(soc_ekf)
    innov = V - V_pred_ekf
    err = soc_true - soc_ekf
    print(f't={t:7.1f}s I={I:7.3f}A V={V:.4f} OCV_true={V_pred_true:.4f} OCV_ekf={V_pred_ekf:.4f} innov={innov:.4f}V err={err*100:.3f}%')

print()
print('--- Cek: apakah ada periode arus=0 di awal? ---')
zero_curr = df[df['Dir_Cur(A)'].abs() < 0.05]
print(f'Jumlah sampel arus ~0: {len(zero_curr)} dari {len(df)} ({100*len(zero_curr)/len(df):.1f}%)')
if len(zero_curr) > 0:
    print(f'Indeks pertama arus~0: {zero_curr.index[0]}')
    print(f'Waktu pertama arus~0: {df.loc[zero_curr.index[0], "Time(S)"]:.1f}s')
