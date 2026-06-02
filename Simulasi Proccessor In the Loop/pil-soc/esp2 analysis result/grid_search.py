"""
Fix validation: Test with dOCV/dSOC floored at a small positive value.
This prevents K[0] from flipping sign in the non-monotonic OCV region.
"""
import csv, math

DATA_DIR = r"c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\Simulasi Proccessor In the Loop\pil-soc\data"
Q_COULOMB = 74874.8
lut_soc_ocv = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
               0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
lut_ocv_val = [2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
               3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
               3.2973, 3.3039, 3.3353, 3.4122, 3.5370]
lut_soc_ecm = [0.0, 0.090902, 0.204618, 0.318054, 0.431697, 0.545421, 0.659070, 0.772787, 0.886430]
lut_r0 = [0.006050, 0.002800, 0.002800, 0.002899, 0.002700, 0.002400, 0.002899, 0.002199, 0.002800]
lut_r1 = [0.009500, 0.002506, 0.002207, 0.002212, 0.002372, 0.002436, 0.002374, 0.002345, 0.002684]
lut_c1 = [11281.15, 20591.86, 24841.48, 15061.40, 20897.75, 19607.70, 15177.97, 16580.74, 24189.08]

def interp1d(x, xd, yd):
    if x <= xd[0]: return yd[0]
    if x >= xd[-1]: return yd[-1]
    for i in range(len(xd)-1):
        if xd[i] <= x <= xd[i+1]:
            t = (x - xd[i]) / (xd[i+1] - xd[i])
            return yd[i] + t * (yd[i+1] - yd[i])
    return yd[0]

def get_ocv(soc): return interp1d(max(0,min(1,soc)), lut_soc_ocv, lut_ocv_val)
def get_docv(soc):
    soc = max(0,min(1,soc)); h=0.005; lo,hi = max(soc-h,0), min(soc+h,1)
    ds = hi-lo; return (get_ocv(hi)-get_ocv(lo))/ds if ds > 1e-6 else 0

def run_ekf(data, soc_true_init, soc_algo_init, Q00, Q11, docv_floor, R_base, R_min, R_max):
    soc_true = soc_true_init
    soc_cc = soc_algo_init
    ekf_x = [soc_algo_init, 0.0]
    ekf_P = [[1.0, 0.0], [0.0, 0.1]]
    
    sum_sq_soc = 0; sum_sq_v = 0; n = 0; time_prev = -1
    
    for t, I, V in data:
        dt = 0 if time_prev < 0 else t - time_prev
        if time_prev >= 0 and dt <= 0: continue
        time_prev = t
        if n == 0: n+=1; continue
        
        soc_true = max(0, min(1, soc_true - I*dt/Q_COULOMB))
        soc_cc = max(0, min(1, soc_cc - I*dt/Q_COULOMB))
        
        sp = max(0,min(1,ekf_x[0])); vp = ekf_x[1]
        R0 = max(interp1d(sp, lut_soc_ecm, lut_r0), 0.0001)
        R1 = max(interp1d(sp, lut_soc_ecm, lut_r1), 0.0001)
        C1 = max(interp1d(sp, lut_soc_ecm, lut_c1), 1.0)
        tau = max(R1*C1, 1e-6)
        soc_pred = max(0, min(1, sp - I*dt/Q_COULOMB))
        alpha = math.exp(-dt/tau) if dt > 0 else 1.0
        vc1_pred = alpha*vp + R1*(1-alpha)*I
        ekf_x[0]=soc_pred; ekf_x[1]=vc1_pred
        
        Pp = [[ekf_P[0][0]+Q00, ekf_P[0][1]*alpha],
              [ekf_P[1][0]*alpha, alpha**2*ekf_P[1][1]+Q11]]
        
        OCV=get_ocv(soc_pred)
        dOCV_raw = get_docv(soc_pred)
        # CRITICAL FIX: Floor the derivative to prevent negative K[0]
        dOCV = max(dOCV_raw, docv_floor)
        Vp=OCV-vc1_pred-I*R0
        
        h0,h1 = dOCV,-1.0
        # Dynamic R with clamping
        R_eff = R_base / (abs(dOCV) + 1e-4)
        R_eff = max(R_eff, R_min)
        R_eff = min(R_eff, R_max)
        
        S = h0*h0*Pp[0][0]+h0*h1*Pp[0][1]+h1*h0*Pp[1][0]+h1*h1*Pp[1][1]+R_eff
        K = [(Pp[0][0]*h0+Pp[0][1]*h1)/S, (Pp[1][0]*h0+Pp[1][1]*h1)/S]
        innov = V - Vp
        ekf_x[0] = max(0, min(1, ekf_x[0]+K[0]*innov)); ekf_x[1] += K[1]*innov
        
        IKH=[[1-K[0]*h0,-K[0]*h1],[-K[1]*h0,1-K[1]*h1]]
        T=[[IKH[0][0]*Pp[0][0]+IKH[0][1]*Pp[1][0],IKH[0][0]*Pp[0][1]+IKH[0][1]*Pp[1][1]],
           [IKH[1][0]*Pp[0][0]+IKH[1][1]*Pp[1][0],IKH[1][0]*Pp[0][1]+IKH[1][1]*Pp[1][1]]]
        ekf_P[0][0]=T[0][0]*IKH[0][0]+T[0][1]*IKH[0][1]+K[0]**2*R_eff
        ekf_P[0][1]=T[0][0]*IKH[1][0]+T[0][1]*IKH[1][1]+K[0]*K[1]*R_eff
        ekf_P[1][0]=T[1][0]*IKH[0][0]+T[1][1]*IKH[0][1]+K[1]*K[0]*R_eff
        ekf_P[1][1]=T[1][0]*IKH[1][0]+T[1][1]*IKH[1][1]+K[1]**2*R_eff
        ekf_P[0][1]=(ekf_P[0][1]+ekf_P[1][0])*0.5; ekf_P[1][0]=ekf_P[0][1]
        ekf_P[0][0]=max(ekf_P[0][0],1e-10); ekf_P[1][1]=max(ekf_P[1][1],1e-10)
        
        err_soc = soc_true - ekf_x[0]; err_v = V - Vp
        sum_sq_soc += err_soc**2; sum_sq_v += err_v**2
        n += 1
    
    rmse_soc = math.sqrt(sum_sq_soc/n)*100 if n > 0 else 999
    rmse_v = math.sqrt(sum_sq_v/n)*1000 if n > 0 else 999
    return rmse_soc, rmse_v

DATASETS = [
    ("clean_h-charge_rest_60m.csv", 0.0, "Charge+Rest"),
    ("clean_h-DCC-4.4A-2.5V.csv", 1.0, "DCC 4.4A"),
    ("clean_h-Dynamic_Profiling_(Urban Load).csv", 1.0, "Dynamic"),
    ("clean_h-charging_7.33A-rest 2h.csv", 0.06, "Charge 7.33A"),
    ("clean_h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv", 0.01, "DCC-CCV-DCC"),
]

# Load datasets
all_data = {}
for fname, soc_init, label in DATASETS:
    path = f"{DATA_DIR}/{fname}"
    rows = []
    with open(path) as f:
        reader = csv.reader(f); next(reader)
        for row in reader:
            if len(row)>=3:
                try: rows.append((float(row[0]),float(row[1]),float(row[2])))
                except: pass
    all_data[label] = (rows, soc_init)
    print(f"Loaded {label}: {len(rows)} samples")

# Grid search over parameters
print("\n" + "="*100)
print("GRID SEARCH: dOCV floor, R_base, R_min, R_max, Q00")
print("="*100)

best_score = 999
best_params = None

for docv_floor in [0.005, 0.01, 0.02, 0.05]:
    for R_base in [0.0002, 0.0005, 0.001, 0.002]:
        for R_min in [0.0001, 0.0002, 0.0005]:
            for R_max in [0.1, 0.5, 1.0, 5.0]:
                for Q00 in [1e-6, 5e-6, 1e-5, 5e-5]:
                    Q11 = 1e-4
                    results = {}
                    all_ok = True
                    max_soc_rmse = 0
                    max_v_rmse = 0
                    
                    for fname, soc_init, label in DATASETS:
                        data, st = all_data[label]
                        sa = st + 0.10 if st < 0.10 else st - 0.10
                        rs, rv = run_ekf(data, st, sa, Q00, Q11, docv_floor, R_base, R_min, R_max)
                        results[label] = (rs, rv)
                        if rs >= 5.0 or rv >= 10.0: all_ok = False
                        max_soc_rmse = max(max_soc_rmse, rs)
                        max_v_rmse = max(max_v_rmse, rv)
                    
                    score = max_soc_rmse + max_v_rmse * 0.1
                    
                    if all_ok:
                        print(f"\n*** PASS *** floor={docv_floor}, Rb={R_base}, Rmin={R_min}, Rmax={R_max}, Q00={Q00:.1e}")
                        for label, (rs, rv) in results.items():
                            print(f"    {label:>15}: RMSE_SoC={rs:.2f}% RMSE_V={rv:.2f}mV")
                        if score < best_score:
                            best_score = score
                            best_params = (docv_floor, R_base, R_min, R_max, Q00)
                    elif max_soc_rmse < 8.0:  # near-pass, print for debugging
                        pass  # skip near-misses to reduce output

if best_params:
    print(f"\n{'='*100}")
    print(f"BEST PARAMS: floor={best_params[0]}, R_base={best_params[1]}, R_min={best_params[2]}, R_max={best_params[3]}, Q00={best_params[4]:.1e}")
    print(f"Score: {best_score:.4f}")
else:
    print("\nNo configuration passed all criteria. Printing best near-misses...")
    # Rerun with relaxed criteria to show best results
    for docv_floor in [0.01, 0.02]:
        for R_base in [0.0005, 0.001]:
            for R_min in [0.0002, 0.0005]:
                for R_max in [0.5, 1.0]:
                    Q00 = 1e-5; Q11 = 1e-4
                    max_s = 0; max_v = 0
                    for fname, soc_init, label in DATASETS:
                        data, st = all_data[label]
                        sa = st + 0.10 if st < 0.10 else st - 0.10
                        rs, rv = run_ekf(data, st, sa, Q00, Q11, docv_floor, R_base, R_min, R_max)
                        max_s = max(max_s, rs); max_v = max(max_v, rv)
                    print(f"  floor={docv_floor}, Rb={R_base}, Rmin={R_min}, Rmax={R_max}: max_SoC={max_s:.2f}%, max_V={max_v:.2f}mV")
