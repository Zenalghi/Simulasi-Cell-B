import csv
import math
import os

Q_AH = 20.798555
Q_COULOMB = 74874.8
lut_soc_ocv = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
lut_ocv_val = [2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625, 3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958, 3.2973, 3.3039, 3.3353, 3.4122, 3.5370]
lut_soc_ecm = [0.0, 0.090902, 0.204618, 0.318054, 0.431697, 0.545421, 0.659070, 0.772787, 0.886430]
lut_r0 = [0.006050, 0.002800, 0.002800, 0.002899, 0.002700, 0.002400, 0.002899, 0.002199, 0.002800]
lut_r1 = [0.009500, 0.002506, 0.002207, 0.002212, 0.002372, 0.002436, 0.002374, 0.002345, 0.002684]
lut_c1 = [11281.15, 20591.86, 24841.48, 15061.40, 20897.75, 19607.70, 15177.97, 16580.74, 24189.08]

def constrain(val, min_val, max_val):
    return max(min_val, min(val, max_val))
def interpolate1D(x, x_data, y_data):
    if x <= x_data[0]: return y_data[0]
    if x >= x_data[-1]: return y_data[-1]
    for i in range(len(x_data) - 1):
        if x_data[i] <= x <= x_data[i + 1]:
            t = (x - x_data[i]) / (x_data[i + 1] - x_data[i])
            return y_data[i] + t * (y_data[i + 1] - y_data[i])
    return y_data[0]
def get_OCV_from_LUT(soc):
    return interpolate1D(constrain(soc, 0.0, 1.0), lut_soc_ocv, lut_ocv_val)
def get_dOCV_dSOC_LUT(soc):
    soc = constrain(soc, 0.0, 1.0)
    h = 0.005
    soc_lo = max(soc - h, 0.0)
    soc_hi = min(soc + h, 1.0)
    dSOC = soc_hi - soc_lo
    if dSOC < 1e-6: return 0.0
    return (get_OCV_from_LUT(soc_hi) - get_OCV_from_LUT(soc_lo)) / dSOC

def runEKFStep(I_meas, V_meas, dt, ekf_x, ekf_P, in_confirmed_rest):
    # Noise parameters to tune
    Q_NOISE_00 = 2e-6
    Q_NOISE_11 = 1e-1
    R_BASE = 0.0001
    R_REST = 0.0001
    
    soc_prev = constrain(ekf_x[0], 0.0, 1.0)
    vc1_prev = ekf_x[1]
    
    R0 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r0), 0.0001)
    R1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r1), 0.0001)
    C1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_c1), 1.0)
    tau = max(R1 * C1, 0.000001)
    
    soc_pred = constrain(soc_prev - (I_meas * dt / Q_COULOMB), 0.0, 1.0)
    alpha = math.exp(-dt / tau) if dt > 0 else 1.0
    vc1_pred = (alpha * vc1_prev) + (R1 * (1.0 - alpha) * I_meas)
    
    ekf_x[0] = soc_pred
    ekf_x[1] = vc1_pred
    
    P_pred = [[0.0, 0.0], [0.0, 0.0]]
    P_pred[0][0] = ekf_P[0][0] + Q_NOISE_00
    P_pred[0][1] = 0.0
    P_pred[1][0] = 0.0
    P_pred[1][1] = (alpha * alpha * ekf_P[1][1]) + Q_NOISE_11
    
    OCV_pred = get_OCV_from_LUT(soc_pred)
    dOCV_dSOC = get_dOCV_dSOC_LUT(soc_pred)
    V_pred = OCV_pred - vc1_pred - (I_meas * R0)
    
    h0 = abs(dOCV_dSOC) + 1e-4
    h1 = -1.0
    
    if in_confirmed_rest:
        R_dynamic = R_REST
    elif abs(I_meas) < 0.05:
        R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-3)
    else:
        R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-4)
    R_dynamic = constrain(R_dynamic, 1e-6, 10.0)
    
    S = (h0 * h0 * P_pred[0][0]) + (h0 * h1 * P_pred[0][1]) + \
        (h1 * h0 * P_pred[1][0]) + (h1 * h1 * P_pred[1][1]) + R_dynamic
    if S < 1e-9: S = 1e-9
    
    K = [0.0, 0.0]
    K[0] = ((P_pred[0][0] * h0) + (P_pred[0][1] * h1)) / S
    K[1] = ((P_pred[1][0] * h0) + (P_pred[1][1] * h1)) / S
    
    K0_eff = K[0]
    innov = V_meas - V_pred
    
    deadband = 0.001
    if abs(innov) < deadband:
        K0_eff *= (abs(innov) / deadband)
        
    ekf_x[0] = max(0.0, min(1.0, ekf_x[0] + K0_eff * innov))
    ekf_x[1] += K[1] * innov
    
    if ekf_x[1] > 0.5: ekf_x[1] = 0.5
    if ekf_x[1] < -0.5: ekf_x[1] = -0.5
    
    I_KH = [[0.0, 0.0], [0.0, 0.0]]
    I_KH[0][0] = 1.0 - (K0_eff * h0)
    I_KH[0][1] = -(K0_eff * h1)
    I_KH[1][0] = -(K[1] * h0)
    I_KH[1][1] = 1.0 - (K[1] * h1)
    
    Temp = [[0.0, 0.0], [0.0, 0.0]]
    Temp[0][0] = I_KH[0][0] * P_pred[0][0] + I_KH[0][1] * P_pred[1][0]
    Temp[0][1] = I_KH[0][0] * P_pred[0][1] + I_KH[0][1] * P_pred[1][1]
    Temp[1][0] = I_KH[1][0] * P_pred[0][0] + I_KH[1][1] * P_pred[1][0]
    Temp[1][1] = I_KH[1][0] * P_pred[0][1] + I_KH[1][1] * P_pred[1][1]
    
    ekf_P[0][0] = Temp[0][0] * I_KH[0][0] + Temp[0][1] * I_KH[0][1] + (K0_eff * K0_eff * R_dynamic)
    ekf_P[0][1] = Temp[0][0] * I_KH[1][0] + Temp[0][1] * I_KH[1][1] + (K0_eff * K[1] * R_dynamic)
    ekf_P[1][0] = Temp[1][0] * I_KH[0][0] + Temp[1][1] * I_KH[0][1] + (K[1] * K0_eff * R_dynamic)
    ekf_P[1][1] = Temp[1][0] * I_KH[1][0] + Temp[1][1] * I_KH[1][1] + (K[1] * K[1] * R_dynamic)
    
    ekf_P[0][1] = (ekf_P[0][1] + ekf_P[1][0]) * 0.5
    ekf_P[1][0] = ekf_P[0][1]
    ekf_P[0][0] = max(ekf_P[0][0], 1e-10)
    ekf_P[1][1] = max(ekf_P[1][1], 1e-10)
    
    return V_pred

files = [
    "dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv",
    "dataset_dcc_0.22c_discharge_constant_2.5v.csv",
    "dataset_dynamic_profiling_urban_load.csv",
    "dataset_fast_charging_0.35c_rest_2h.csv",
    "dataset_capacity_measurement_dcc_cc_cv_dcc.csv"
]
for filename in files:
    filepath = os.path.join("data", filename)
    with open(filepath, 'r') as f:
        lines = f.readlines()
    data = []
    for line in lines[1:]: # skip header
        parts = line.strip().split(',')
        if len(parts) >= 3:
            data.append((float(parts[0]), float(parts[1]), float(parts[2])))
            
    for offset in [0.0, 0.05, 0.10]:
        soc_true = 0.5
        if "charge_rest" in filename: soc_true = 0.0
        elif "DCC-4.4A" in filename: soc_true = 1.0
        elif "Urban Load" in filename: soc_true = 1.0
        elif "charging_7.33A" in filename: soc_true = 0.06
        elif "CCV" in filename: soc_true = 0.01
        
        soc_algo_start = (soc_true + offset) if soc_true < 0.1 else (soc_true - offset)
        ekf_x = [soc_algo_start, 0.0]
        ekf_P = [[abs(offset) * 50.0 + 0.01, 0.0], [0.0, 0.001]]
        
        sum_sq_err_ekf_soc = 0.0
        sum_sq_err_ekf_v = 0.0
        total_samples = 0
        time_prev = data[0][0]
        
        rest_counter_s = 0
        in_confirmed_rest = False
        
        for i in range(1, len(data)):
            t, current, voltage = data[i]
            dt = t - time_prev
            if dt <= 0: continue
            time_prev = t
            soc_true = constrain(soc_true - (current * dt / Q_COULOMB), 0.0, 1.0)
            
            if abs(current) < 0.05:
                rest_counter_s += dt
                if rest_counter_s >= 30:
                    in_confirmed_rest = True
            else:
                rest_counter_s = 0
                in_confirmed_rest = False
                
            v_pred = runEKFStep(current, voltage, dt, ekf_x, ekf_P, in_confirmed_rest)
            err_soc = soc_true - ekf_x[0]
            err_v = voltage - v_pred
            sum_sq_err_ekf_soc += err_soc * err_soc
            sum_sq_err_ekf_v += err_v * err_v
            total_samples += 1
            if offset == 0.1 and "DCC-4.4" in filename and total_samples < 5:
                print(f"Step {total_samples}: true={soc_true:.4f}, ekf={ekf_x[0]:.4f}, K0={ekf_P[0][0]:.4f}, err_v={err_v:.4f}")
        rmse_soc = math.sqrt(sum_sq_err_ekf_soc / total_samples) * 100.0
        rmse_v = math.sqrt(sum_sq_err_ekf_v / total_samples) * 1000.0
        print(f"File: {filename[:15]} offset: {offset} -> SOC: {rmse_soc:.2f}%, V: {rmse_v:.2f}mV (Final SOC true: {soc_true:.4f}, EKF SOC: {ekf_x[0]:.4f})", flush=True)

