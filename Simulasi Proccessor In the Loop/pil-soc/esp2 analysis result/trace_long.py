"""
Long-term EKF trace: sample every 100 steps for charge_rest_60m
to see if EKF tracks correctly over the full cycle.
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

rows = []
with open(f"{DATA_DIR}/clean_h-charge_rest_60m.csv") as f:
    reader = csv.reader(f); next(reader)
    for row in reader:
        if len(row) >= 3:
            rows.append((float(row[0]), float(row[1]), float(row[2])))

soc_true = 0.0; soc_cc = 0.10; ekf_x = [0.10, 0.0]
ekf_P = [[1.0, 0.0], [0.0, 0.1]]; Q00, Q11 = 1e-5, 1e-4
time_prev = -1; n = 0

# Test with CLAMPED R strategy
def R_func(dOCV):
    R = 0.0005 / (abs(dOCV) + 1e-4)
    return max(R, 0.0005)  # floor only

print(f"{'Step':>5} {'t':>6} {'I':>6} {'V':>6} | {'true':>7} {'cc':>7} {'ekf':>7} | {'err_cc':>7} {'err_ekf':>7} | {'dOCV':>6} {'R':>8} {'K0':>8}")
print("-"*110)

for step, (t, I, V) in enumerate(rows):
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
    
    Pp = [[ekf_P[0][0]+Q00, ekf_P[0][1]*alpha],[ekf_P[1][0]*alpha, alpha**2*ekf_P[1][1]+Q11]]
    OCV=get_ocv(soc_pred); dOCV=get_docv(soc_pred); Vp=OCV-vc1_pred-I*R0
    h0,h1 = dOCV,-1.0; R_eff = R_func(dOCV)
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
    
    if step % 200 == 0 or step < 5 or step > len(rows)-5:
        print(f"{step:5d} {t:6.0f} {I:6.2f} {V:6.3f} | {soc_true:7.4f} {soc_cc:7.4f} {ekf_x[0]:7.4f} | {(soc_true-soc_cc)*100:7.2f}% {(soc_true-ekf_x[0])*100:7.2f}% | {dOCV:6.2f} {R_eff:8.5f} {K[0]:8.5f}")
    n += 1

print(f"\nFinal: true={soc_true:.4f} cc={soc_cc:.4f} ekf={ekf_x[0]:.4f}")
print(f"CC error: {(soc_true-soc_cc)*100:.2f}%")
print(f"EKF error: {(soc_true-ekf_x[0])*100:.2f}%")
