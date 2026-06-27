"""
Full EKF simulation matching ESP32 main.cpp logic.
Tests different R tuning strategies to find parameters that achieve:
  - RMSE SoC < 5% on all datasets
  - RMSE V < 10 mV on all datasets
"""
import csv
import os
import math

DATA_DIR = r"c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\Simulasi Proccessor In the Loop\pil-soc\data"

# Battery model
Q_COULOMB = 74874.8

# OCV LUT
lut_soc_ocv = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
               0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
lut_ocv_val = [2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
               3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
               3.2973, 3.3039, 3.3353, 3.4122, 3.5370]

# ECM parameters
lut_soc_ecm = [0.0, 0.090902, 0.204618, 0.318054, 0.431697, 0.545421, 0.659070, 0.772787, 0.886430]
lut_r0 = [0.006050, 0.002800, 0.002800, 0.002899, 0.002700, 0.002400, 0.002899, 0.002199, 0.002800]
lut_r1 = [0.009500, 0.002506, 0.002207, 0.002212, 0.002372, 0.002436, 0.002374, 0.002345, 0.002684]
lut_c1 = [11281.15, 20591.86, 24841.48, 15061.40, 20897.75, 19607.70, 15177.97, 16580.74, 24189.08]

def interp1d(x, x_data, y_data):
    if x <= x_data[0]: return y_data[0]
    if x >= x_data[-1]: return y_data[-1]
    for i in range(len(x_data)-1):
        if x_data[i] <= x <= x_data[i+1]:
            t = (x - x_data[i]) / (x_data[i+1] - x_data[i])
            return y_data[i] + t * (y_data[i+1] - y_data[i])
    return y_data[0]

def get_ocv(soc):
    return interp1d(max(0.0, min(1.0, soc)), lut_soc_ocv, lut_ocv_val)

def get_docv(soc):
    soc = max(0.0, min(1.0, soc))
    h = 0.005
    lo = max(soc - h, 0.0)
    hi = min(soc + h, 1.0)
    ds = hi - lo
    if ds < 1e-6: return 0.0
    return (get_ocv(hi) - get_ocv(lo)) / ds

def load_dataset(filepath):
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 3: continue
            try:
                t = float(row[0].strip())
                i = float(row[1].strip())
                v = float(row[2].strip())
                rows.append((t, i, v))
            except: continue
    return rows

def run_ekf_sim(data, soc_true_init, soc_algo_init, Q00, Q11, r_func, P00_init=1.0):
    """Run EKF simulation with given parameters, return metrics."""
    # State
    soc_cc = soc_algo_init
    ekf_x = [soc_algo_init, 0.0]
    ekf_P = [[P00_init, 0.0], [0.0, 0.1]]
    soc_true = soc_true_init
    
    sum_sq_soc = 0.0
    sum_sq_v = 0.0
    sum_abs_soc = 0.0
    sum_abs_v = 0.0
    n = 0
    time_prev = -1.0
    
    for t, current, voltage in data:
        dt = 0.0 if time_prev < 0 else (t - time_prev)
        if time_prev >= 0 and dt <= 0:
            continue
        time_prev = t
        
        if n == 0:
            n += 1
            continue
        
        # Update true SoC
        soc_true = max(0.0, min(1.0, soc_true - current * dt / Q_COULOMB))
        
        # CC step
        soc_cc = max(0.0, min(1.0, soc_cc - current * dt / Q_COULOMB))
        
        # EKF step
        soc_prev = max(0.0, min(1.0, ekf_x[0]))
        vc1_prev = ekf_x[1]
        
        R0 = max(interp1d(soc_prev, lut_soc_ecm, lut_r0), 0.0001)
        R1 = max(interp1d(soc_prev, lut_soc_ecm, lut_r1), 0.0001)
        C1 = max(interp1d(soc_prev, lut_soc_ecm, lut_c1), 1.0)
        tau = max(R1 * C1, 0.000001)
        
        soc_pred = max(0.0, min(1.0, soc_prev - current * dt / Q_COULOMB))
        alpha = math.exp(-dt / tau) if dt > 0 else 1.0
        vc1_pred = alpha * vc1_prev + R1 * (1.0 - alpha) * current
        
        ekf_x[0] = soc_pred
        ekf_x[1] = vc1_pred
        
        # P prediction
        P_pred = [[0,0],[0,0]]
        P_pred[0][0] = ekf_P[0][0] + Q00
        P_pred[0][1] = ekf_P[0][1] * alpha
        P_pred[1][0] = ekf_P[1][0] * alpha
        P_pred[1][1] = alpha * alpha * ekf_P[1][1] + Q11
        
        # Measurement update
        OCV_pred = get_ocv(soc_pred)
        dOCV = get_docv(soc_pred)
        V_pred = OCV_pred - vc1_pred - current * R0
        
        h0 = dOCV
        h1 = -1.0
        
        R_eff = r_func(dOCV, current)
        
        S = h0*h0*P_pred[0][0] + h0*h1*P_pred[0][1] + h1*h0*P_pred[1][0] + h1*h1*P_pred[1][1] + R_eff
        
        K = [0, 0]
        K[0] = (P_pred[0][0]*h0 + P_pred[0][1]*h1) / S
        K[1] = (P_pred[1][0]*h0 + P_pred[1][1]*h1) / S
        
        innov = voltage - V_pred
        ekf_x[0] = max(0.0, min(1.0, ekf_x[0] + K[0] * innov))
        ekf_x[1] = ekf_x[1] + K[1] * innov
        
        # Joseph form P update
        IKH = [[1.0 - K[0]*h0, -K[0]*h1],
               [-K[1]*h0, 1.0 - K[1]*h1]]
        
        Tmp = [[IKH[0][0]*P_pred[0][0]+IKH[0][1]*P_pred[1][0], IKH[0][0]*P_pred[0][1]+IKH[0][1]*P_pred[1][1]],
               [IKH[1][0]*P_pred[0][0]+IKH[1][1]*P_pred[1][0], IKH[1][0]*P_pred[0][1]+IKH[1][1]*P_pred[1][1]]]
        
        ekf_P[0][0] = Tmp[0][0]*IKH[0][0]+Tmp[0][1]*IKH[0][1]+K[0]*K[0]*R_eff
        ekf_P[0][1] = Tmp[0][0]*IKH[1][0]+Tmp[0][1]*IKH[1][1]+K[0]*K[1]*R_eff
        ekf_P[1][0] = Tmp[1][0]*IKH[0][0]+Tmp[1][1]*IKH[0][1]+K[1]*K[0]*R_eff
        ekf_P[1][1] = Tmp[1][0]*IKH[1][0]+Tmp[1][1]*IKH[1][1]+K[1]*K[1]*R_eff
        
        ekf_P[0][1] = (ekf_P[0][1]+ekf_P[1][0])*0.5
        ekf_P[1][0] = ekf_P[0][1]
        ekf_P[0][0] = max(ekf_P[0][0], 1e-10)
        ekf_P[1][1] = max(ekf_P[1][1], 1e-10)
        
        # Accumulate errors
        err_soc = soc_true - ekf_x[0]
        err_v = voltage - V_pred
        sum_sq_soc += err_soc**2
        sum_sq_v += err_v**2
        sum_abs_soc += abs(err_soc)
        sum_abs_v += abs(err_v)
        n += 1
    
    rmse_soc = math.sqrt(sum_sq_soc / n) * 100.0 if n > 0 else 999
    rmse_v = math.sqrt(sum_sq_v / n) * 1000.0 if n > 0 else 999
    mae_soc = (sum_abs_soc / n) * 100.0 if n > 0 else 999
    mae_v = (sum_abs_v / n) * 1000.0 if n > 0 else 999
    
    return rmse_soc, rmse_v, mae_soc, mae_v

# Dataset configs
DATASETS = [
    ("dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv", 0.0, "Charge+Rest"),
    ("dataset_dcc_0.22c_discharge_constant_2.5v.csv", 1.0, "DCC 4.4A"),
    ("dataset_dynamic_profiling_urban_load.csv", 1.0, "Dynamic"),
    ("dataset_fast_charging_0.35c_rest_2h.csv", 0.06, "Charge 7.33A"),
    ("dataset_capacity_measurement_dcc_cc_cv_dcc.csv", 0.01, "DCC-CCV-DCC"),
]

# R-matrix strategies to test
def r_strategy_old_heuristic(dOCV, I):
    """Old heuristic from esp.md"""
    R = 0.0002
    if abs(I) < 0.05:
        R *= 0.5
    elif I < 0:
        R *= 10.0
    else:
        R *= 5.0
    return R

def r_strategy_dynamic_v1(dOCV, I):
    """Current broken implementation"""
    return 0.0005 / (abs(dOCV) + 1e-4)

def r_strategy_clamped(dOCV, I):
    """Dynamic with proper clamping"""
    base_R = 0.0005
    R = base_R / (abs(dOCV) + 1e-4)
    R = max(R, 0.0005)  # floor: minimum measurement noise
    R = min(R, 0.5)     # ceiling: max distrust
    return R

def r_strategy_squared(dOCV, I):
    """Use squared slope for gentler scaling"""
    base_R = 0.002
    R = base_R / (dOCV * dOCV + 0.04)
    R = max(R, 0.0005)
    R = min(R, 1.0)
    return R

def r_strategy_tuned(dOCV, I):
    """Tuned strategy: moderate dynamic range with rest boost"""
    base_R = 0.001
    R = base_R / (abs(dOCV) + 0.005)
    R = max(R, 0.0005)
    R = min(R, 0.5)
    return R

def r_strategy_hybrid(dOCV, I):
    """Hybrid: dynamic observability + rest detection"""
    base_R = 0.0005
    R = base_R / (abs(dOCV) + 0.005)
    R = max(R, 0.0002)  # minimum noise floor
    R = min(R, 0.5)     # maximum distrust
    # During rest, voltage = OCV, very trustworthy
    if abs(I) < 0.05:
        R = min(R, 0.0005)
    return R

strategies = {
    "Old Heuristic": (r_strategy_old_heuristic, 5e-6, 1e-4, 0.5),
    "Dynamic v1 (broken)": (r_strategy_dynamic_v1, 1e-5, 1e-4, 1.0),
    "Clamped": (r_strategy_clamped, 1e-5, 1e-4, 1.0),
    "Squared": (r_strategy_squared, 1e-5, 1e-4, 1.0),
    "Tuned": (r_strategy_tuned, 1e-5, 1e-4, 1.0),
    "Hybrid": (r_strategy_hybrid, 1e-5, 1e-4, 1.0),
}

# Load all datasets
print("Loading datasets...")
all_data = {}
for fname, soc_init, label in DATASETS:
    path = os.path.join(DATA_DIR, fname)
    if os.path.exists(path):
        all_data[label] = (load_dataset(path), soc_init)
        print(f"  {label}: {len(all_data[label][0])} samples")
    else:
        print(f"  {label}: FILE NOT FOUND at {path}")

print()

# Run all strategies
for strat_name, (r_func, Q00, Q11, P00) in strategies.items():
    print(f"\n{'='*90}")
    print(f"  Strategy: {strat_name}")
    print(f"  Q00={Q00:.1e}, Q11={Q11:.1e}, P00={P00}")
    print(f"{'='*90}")
    print(f"{'Dataset':>15} {'RMSE SoC%':>10} {'RMSE V mV':>10} {'MAE SoC%':>10} {'MAE V mV':>10} {'Pass?':>6}")
    print("-"*90)
    
    all_pass = True
    for fname, soc_init, label in DATASETS:
        if label not in all_data: continue
        data, soc_true_init = all_data[label]
        soc_algo = soc_true_init + 0.10 if soc_true_init < 0.10 else soc_true_init - 0.10
        
        rmse_soc, rmse_v, mae_soc, mae_v = run_ekf_sim(data, soc_true_init, soc_algo, Q00, Q11, r_func, P00)
        
        ok = rmse_soc < 5.0 and rmse_v < 10.0
        if not ok: all_pass = False
        
        print(f"{label:>15} {rmse_soc:10.4f} {rmse_v:10.4f} {mae_soc:10.4f} {mae_v:10.4f} {'OK' if ok else 'FAIL':>6}")
    
    print(f"\n  --> {'ALL PASS' if all_pass else 'SOME FAILED'}")
