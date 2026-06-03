"""
EKF Parameter Optimizer — mencari parameter terbaik untuk memenuhi:
  - RMSE SoC EKF < 5% untuk semua dataset dan semua offset
  - RMSE V EKF   < 10 mV untuk semua dataset dan semua offset

Analisis dari hasil pengujian sebelumnya:
  - esp8:  Q_00=1e-6, Q_11=1e-1, P[0][0]=1.0  → gagal di 5% & 10% offset (tidak konvergen)
  - esp9:  Q_00=1e-5, Q_11=5e-3, P=offset^2   → banyak > 5% (esp Dynamic, DCC-4.4A)
  - esp10: Q_00=1e-5, Q_11=5e-3, P=offset^2   → sama, beberapa > 8%
  - esp11: R_STEEP/FLAT berbeda → divergen (gain terlalu kecil, RMSE 57%)
  - esp12: Q_00=1e-6, Q_11=1e-1, deadband 3mV → bagus tapi charging_7.3A offset10% = 33%!
  - esp13: Q_00=2e-6, Q_11=1e-1, P=offset^2+0.01, P[1][1]=0.001 → Dynamic 5%=5.34% FAIL
           dan charging_7.33A offset10% = 33.74% FAIL BESAR

Masalah utama yang teridentifikasi:
1. Dataset 'charging_7.33A-rest 2h' offset 10% → selalu gagal di esp12&esp13
   → SoC awal = 0.06, dengan offset +10% → 0.16, tapi SoC_true = 0.06
   → Ini dataset CHARGING dari SoC rendah ke tinggi
   → Charging: soc_algo_start = soc_true + offset (BUKAN soc_true - offset!)
   → Cek logika offset di kode C++: 
      float soc_algo_start = (soc_true < 0.10f) ? (soc_true + offset_pct_val) : (soc_true - offset_pct_val);
   → Artinya untuk charging_7.33A (soc_true=0.06 < 0.10), init = 0.06 + 0.10 = 0.16
   → Tapi seiring waktu, soc_true naik, soc_ekf juga naik dengan CC offset sehingga error TIDAK berkurang
   → EKF harus mengandalkan voltage measurement untuk KORREKSI ke bawah (negatif) tapi karena charging
      OCV juga naik, susah membedakan

2. Dynamic Profiling offset 5% → 5.34% (sedikit di atas target)
   → Perlu tuning P[0][0] lebih besar untuk konvergensi lebih cepat

Strategi baru:
- P[0][0] = abs(offset)*100 + 0.05  (lebih agresif awal)  
- P[1][1] = 0.001 (tetap kecil untuk stabilitas voltage)
- Q_00 = 5e-6 (sedikit lebih besar dari esp13 untuk respons lebih cepat)
- Q_11 = 5e-2 (dikurangi dari 1e-1 untuk voltage lebih stabil)
- Deadband = 0.5mV (tighter dari 1mV)
- R_REST = 5e-5 (lebih agresif saat rest)
- Khusus dataset charging dari SoC<10%: logika offset harus membalik
"""

import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(r'c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\Simulasi Proccessor In the Loop\pil-soc\data')

# ── OCV-SoC LUT ──────────────────────────────────────────────
lut_soc_ocv = np.array([
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00
])
lut_ocv_val = np.array([
    2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
    3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
    3.2973, 3.3039, 3.3353, 3.4122, 3.5370
])
lut_soc_ecm = np.array([0.0, 0.090902, 0.204618, 0.318054, 0.431697,
                         0.545421, 0.659070, 0.772787, 0.886430])
lut_r0 = np.array([0.006050, 0.002800, 0.002800, 0.002899, 0.002700,
                    0.002400, 0.002899, 0.002199, 0.002800])
lut_r1 = np.array([0.009500, 0.002506, 0.002207, 0.002212, 0.002372,
                    0.002436, 0.002374, 0.002345, 0.002684])
lut_c1 = np.array([11281.15, 20591.86, 24841.48, 15061.40, 20897.75,
                    19607.70, 15177.97, 16580.74, 24189.08])

Q_COULOMB = 74874.8

SOC_INIT_MAP = {
    'clean_h-charge_rest_60m.csv':                      0.00,
    'clean_h-DCC-4.4A-2.5V.csv':                        1.00,
    'clean_h-Dynamic_Profiling_(Urban Load).csv':        1.00,
    'clean_h-charging_7.33A-rest 2h.csv':               0.06,
    'clean_h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv': 0.01,
}

def interp1d(x, xd, yd):
    if x <= xd[0]: return yd[0]
    if x >= xd[-1]: return yd[-1]
    for i in range(len(xd)-1):
        if xd[i] <= x <= xd[i+1]:
            t = (x - xd[i]) / (xd[i+1] - xd[i])
            return yd[i] + t*(yd[i+1]-yd[i])
    return yd[0]

def get_OCV(soc):
    return interp1d(np.clip(soc,0,1), lut_soc_ocv, lut_ocv_val)

def get_dOCV(soc):
    h = 0.005
    sl = max(np.clip(soc,0,1)-h, 0)
    sh = min(np.clip(soc,0,1)+h, 1)
    ds = sh - sl
    if ds < 1e-6: return 0.0
    return (get_OCV(sh)-get_OCV(sl))/ds


def simulate(params, verbose=False):
    """
    params = {
      Q00, Q11, R_BASE, R_REST,
      REST_THRESH, REST_SETTLE,
      DEADBAND,
      P00_scale, P00_base,  # P[0][0] = abs(offset)*P00_scale + P00_base
      P11_init,             # P[1][1] init
    }
    Returns: dict {(fname, offset): {'rmse_soc', 'rmse_v'}}
    """
    Q00         = params['Q00']
    Q11         = params['Q11']
    R_BASE      = params['R_BASE']
    R_REST      = params['R_REST']
    REST_THRESH = params.get('REST_THRESH', 0.05)
    REST_SETTLE = params.get('REST_SETTLE', 30)
    DEADBAND    = params.get('DEADBAND', 0.001)
    P00_scale   = params.get('P00_scale', 50.0)
    P00_base    = params.get('P00_base', 0.01)
    P11_init    = params.get('P11_init', 0.001)
    R_eps_rest  = params.get('R_eps_rest', 1e-3)
    R_eps_act   = params.get('R_eps_act', 1e-4)

    results = {}
    for fname, soc_init in SOC_INIT_MAP.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath)
        times    = df['Time(S)'].values
        currents = df['Dir_Cur(A)'].values
        voltages = df['Vol(V)'].values

        for offset in [0.0, 0.05, 0.10]:
            # Offset logic identical to main.cpp
            if soc_init < 0.10:
                soc_start = np.clip(soc_init + offset, 0, 1)
            else:
                soc_start = np.clip(soc_init - offset, 0, 1)

            soc_true = soc_init
            ekf_x = np.array([soc_start, 0.0])
            ekf_P = np.array([
                [abs(offset)*P00_scale + P00_base, 0.0],
                [0.0, P11_init]
            ])
            rest_ctr = 0
            in_rest  = False
            t_prev   = -1.0
            first    = True

            sq_soc, sq_v, n = 0.0, 0.0, 0

            for k in range(len(times)):
                t = times[k]; I = currents[k]; V = voltages[k]
                dt = 0.0 if t_prev < 0 else (t - t_prev)
                if t_prev >= 0 and dt <= 0:
                    continue
                t_prev = t

                if first:
                    first = False
                    continue

                soc_true = np.clip(soc_true - I*dt/Q_COULOMB, 0, 1)

                # Rest detection
                if abs(I) < REST_THRESH:
                    rest_ctr += int(dt)
                    if rest_ctr >= REST_SETTLE: in_rest = True
                else:
                    rest_ctr = 0; in_rest = False

                # EKF step
                sp = np.clip(ekf_x[0], 0, 1)
                vp = ekf_x[1]
                R0  = max(interp1d(sp, lut_soc_ecm, lut_r0), 1e-4)
                R1  = max(interp1d(sp, lut_soc_ecm, lut_r1), 1e-4)
                C1  = max(interp1d(sp, lut_soc_ecm, lut_c1), 1.0)
                tau = max(R1*C1, 1e-6)

                soc_pred = np.clip(sp - I*dt/Q_COULOMB, 0, 1)
                alpha    = np.exp(-dt/tau) if dt > 0 else 1.0
                vc1_pred = alpha*vp + R1*(1-alpha)*I

                P_pred = np.array([
                    [ekf_P[0,0]+Q00, 0.0],
                    [0.0, alpha**2*ekf_P[1,1]+Q11]
                ])

                dOCV  = get_dOCV(soc_pred)
                V_pred = get_OCV(soc_pred) - vc1_pred - I*R0
                h0 = dOCV + 1e-4
                h1 = -1.0
                H  = np.array([h0, h1])

                if in_rest:
                    R_dyn = R_REST
                elif abs(I) < 0.05:
                    R_dyn = R_BASE / (abs(dOCV) + R_eps_rest)
                else:
                    R_dyn = R_BASE / (abs(dOCV) + R_eps_act)
                R_dyn = np.clip(R_dyn, 1e-4, 10.0)

                S = H @ P_pred @ H + R_dyn
                S = max(S, 1e-9)
                K = P_pred @ H / S

                innov  = V - V_pred
                K0_eff = K[0]*(abs(innov)/DEADBAND) if abs(innov) < DEADBAND else K[0]

                ekf_x[0] = np.clip(soc_pred + K0_eff*innov, 0, 1)
                ekf_x[1] = np.clip(vc1_pred + K[1]*innov, -0.5, 0.5)

                I_KH = np.eye(2) - np.outer([K0_eff, K[1]], H)
                ekf_P = I_KH @ P_pred @ I_KH.T + np.outer([K0_eff,K[1]],[K0_eff,K[1]])*R_dyn
                ekf_P = (ekf_P + ekf_P.T)/2
                ekf_P[0,0] = max(ekf_P[0,0], 1e-10)
                ekf_P[1,1] = max(ekf_P[1,1], 1e-10)

                sq_soc += (soc_true - ekf_x[0])**2
                sq_v   += (V - V_pred)**2
                n      += 1

            if n > 0:
                results[(fname, offset)] = {
                    'rmse_soc': np.sqrt(sq_soc/n)*100,
                    'rmse_v':   np.sqrt(sq_v/n)*1000,
                }

    return results


def evaluate(params):
    """Return max RMSE SoC and max RMSE V across all tests, plus list of failures."""
    res = simulate(params)
    max_soc, max_v = 0, 0
    failures = []
    for key, r in res.items():
        fname, off = key
        s, v = r['rmse_soc'], r['rmse_v']
        if s > max_soc: max_soc = s
        if v > max_v:   max_v = v
        if s >= 5.0 or v >= 10.0:
            failures.append(f"  ❌ {fname[:25]} off={int(off*100)}%: SoC={s:.3f}% V={v:.2f}mV")
    return max_soc, max_v, failures


print("=" * 70)
print("ANALISIS HISTORIS PENGUJIAN ESP8–ESP13")
print("=" * 70)

history = {
    'esp8':  {'Q00':1e-6,  'Q11':1e-1, 'P_init':'1.0', 'notes':'P[1][1]=0.1, offset fix'},
    'esp9':  {'Q00':1e-5,  'Q11':5e-3, 'P_init':'offset^2+0.01', 'notes':'Q11 kecil'},
    'esp10': {'Q00':1e-5,  'Q11':5e-3, 'P_init':'offset^2+0.01', 'notes':'sama esp9'},
    'esp11': {'Q00':5e-6,  'Q11':1e-4, 'P_init':'0.02', 'notes':'R_STEEP/FLAT → divergen'},
    'esp12': {'Q00':1e-6,  'Q11':1e-1, 'P_init':'offset^2+0.01, P11=0.1', 'notes':'deadband 3mV'},
    'esp13': {'Q00':2e-6,  'Q11':1e-1, 'P_init':'offset^2+0.01, P11=0.001', 'notes':'current'},
}

BEST_RESULT = { # dari esp12 (terbaik kecuali charging_7.33A off10%)
    'esp12 terbaik': {
        'SoC max': '15.73% ❌ (charging_7.33 off10%)',
        'V max':   '28.22mV ❌ (charging_7.33 off10%)',
        'catatan': 'Semua OK kecuali 1 kasus: charging_7.33A offset 10%'
    }
}

print("\nMasalah utama yang diidentifikasi dari esp13:")
print("  1. Dynamic_Prof offset 5%  → RMSE SoC = 5.34% (FAIL, sedikit di atas 5%)")
print("  2. charging_7.33A offset10% → RMSE SoC = 33.74% FAIL BESAR")
print("  3. charging_7.33A offset10% → RMSE V = 51.44mV FAIL BESAR")
print()
print("Root cause charging_7.33A offset 10%:")
print("  - soc_true_init = 0.06, offset = +0.10 → soc_start = 0.16")
print("  - Dataset ini adalah CHARGING: soc naik 0.06 → ~1.00")  
print("  - Offset error = +0.10 tapi charging, jadi error ACCUMULATE karena")
print("    EKF tidak bisa koreksi efektif di daerah flat 10-20% SoC")
print("  - P[0][0] init = 0.10*50+0.01 = 5.01 → terlalu besar → Kalman gain besar")
print("    → koreksi over-aggressive di daerah flat → divergen")
print()

# ── Cari parameter optimal ────────────────────────────────────
print("=" * 70)
print("MENCARI PARAMETER OPTIMAL")
print("=" * 70)

# Baseline test dulu (esp13)
base = {
    'Q00': 2e-6, 'Q11': 1e-1, 'R_BASE': 1e-4, 'R_REST': 1e-4,
    'REST_THRESH': 0.05, 'REST_SETTLE': 30, 'DEADBAND': 1e-3,
    'P00_scale': 50.0, 'P00_base': 0.01, 'P11_init': 0.001,
    'R_eps_rest': 1e-3, 'R_eps_act': 1e-4,
}
ms, mv, fails = evaluate(base)
print(f"\n[Baseline esp13] max_SoC={ms:.3f}%, max_V={mv:.3f}mV")
for f in fails[:5]: print(f)

# Grid search sederhana
print("\n[Grid Search]")
best_score = 1e9
best_params = None

# Kunci: charging_7.33A off10% gagal karena P terlalu besar
# Perlu batasi P[0][0] max → gunakan sqrt atau cap
candidate_configs = [
    # P00_scale, P00_base, Q00,  Q11,   R_BASE,  R_REST,  DEADBAND, P11
    (20.0, 0.02,  2e-6,  8e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (15.0, 0.02,  3e-6,  8e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (10.0, 0.02,  3e-6,  8e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (10.0, 0.02,  5e-6,  8e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (10.0, 0.02,  3e-6,  5e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (10.0, 0.02,  3e-6,  5e-2,  1e-4, 8e-5, 2e-4, 5e-4),
    (8.0,  0.02,  3e-6,  5e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (8.0,  0.02,  5e-6,  5e-2,  1e-4, 8e-5, 5e-4, 5e-4),
    (8.0,  0.02,  5e-6,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (8.0,  0.02,  5e-6,  5e-2,  2e-4, 5e-5, 5e-4, 5e-4),
    (8.0,  0.02,  3e-6,  1e-1,  1e-4, 5e-5, 5e-4, 5e-4),  
    (5.0,  0.02,  3e-6,  1e-1,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  3e-6,  1e-1,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  5e-6,  1e-1,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  5e-6,  1e-1,  2e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  5e-6,  8e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  8e-6,  8e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    # Lebih agresif
    (5.0,  0.05,  1e-5,  8e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  1e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  1e-5,  5e-2,  2e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  1e-5,  3e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  2e-5,  3e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  2e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  1e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  2e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  2e-5,  5e-2,  2e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  3e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  3e-5,  3e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (3.0,  0.05,  5e-5,  3e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    # R_eps berbeda
    (5.0,  0.05,  1e-5,  5e-2,  1e-4, 5e-5, 5e-4, 5e-4),
    (5.0,  0.05,  1e-5,  5e-2,  1e-4, 5e-5, 5e-4, 1e-3),
    (5.0,  0.05,  1e-5,  5e-2,  1e-4, 5e-5, 5e-4, 2e-3),
]

results_list = []
for cfg in candidate_configs:
    ps, pb, q00, q11, rb, rr, db, p11 = cfg
    p = {
        'Q00': q00, 'Q11': q11, 'R_BASE': rb, 'R_REST': rr,
        'REST_THRESH': 0.05, 'REST_SETTLE': 30, 'DEADBAND': db,
        'P00_scale': ps, 'P00_base': pb, 'P11_init': p11,
        'R_eps_rest': 1e-3, 'R_eps_act': 1e-4,
    }
    ms, mv, fails = evaluate(p)
    score = ms + mv/10.0  # weighted score
    results_list.append((score, ms, mv, p, fails))
    if ms < 5.0 and mv < 10.0:
        print(f"  ✅ P00s={ps:.0f} P00b={pb} Q00={q00:.0e} Q11={q11:.0e} R={rb:.0e} R_REST={rr:.0e} DB={db:.0e} P11={p11:.0e} → SoC={ms:.3f}% V={mv:.3f}mV")
    else:
        status = "⚠️ " if ms < 5.0 or mv < 10.0 else "❌"
        print(f"  {status} P00s={ps:.0f} Q00={q00:.0e} Q11={q11:.0e} → SoC={ms:.3f}% V={mv:.3f}mV  {len(fails)} fails")

results_list.sort(key=lambda x: x[0])

print("\n" + "="*70)
print("TOP 5 KANDIDAT PARAMETER:")
print("="*70)
for i, (score, ms, mv, p, fails) in enumerate(results_list[:5]):
    print(f"\n#{i+1} score={score:.4f}  max_SoC={ms:.3f}%  max_V={mv:.3f}mV")
    print(f"    Q00={p['Q00']:.1e} Q11={p['Q11']:.1e} R_BASE={p['R_BASE']:.1e} R_REST={p['R_REST']:.1e}")
    print(f"    DEADBAND={p['DEADBAND']:.1e} P00_scale={p['P00_scale']} P00_base={p['P00_base']} P11={p['P11_init']:.1e}")
    for f in fails:
        print(f"    {f}")

# Best params
best_score, best_ms, best_mv, best_p, best_fails = results_list[0]
print(f"\n{'='*70}")
print("PARAMETER TERPILIH:")
print(f"{'='*70}")
print(f"  Q_NOISE_00  = {best_p['Q00']:.1e}f")
print(f"  Q_NOISE_11  = {best_p['Q11']:.1e}f")
print(f"  R_BASE      = {best_p['R_BASE']:.1e}f")
print(f"  R_REST      = {best_p['R_REST']:.1e}f")
print(f"  DEADBAND    = {best_p['DEADBAND']:.1e}f")
print(f"  P00_scale   = {best_p['P00_scale']}f")
print(f"  P00_base    = {best_p['P00_base']}f")
print(f"  P11_init    = {best_p['P11_init']:.1e}f")
print(f"\n  Result → max SoC RMSE = {best_ms:.4f}% | max V RMSE = {best_mv:.4f}mV")
if best_ms < 5.0 and best_mv < 10.0:
    print("  🎉 TARGET TERCAPAI!")
else:
    print("  ⚠️ Belum tercapai, perlu strategi lanjut")
    if best_fails:
        for f in best_fails:
            print(f"  {f}")
