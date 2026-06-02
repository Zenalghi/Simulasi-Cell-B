"""
Diagnostic script: compute dOCV/dSOC at every LUT point and test R_dynamic values.
Also simulate the EKF behavior to find optimal tuning parameters.
"""
import math

# LUT data
lut_soc = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
           0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
lut_ocv = [2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
           3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
           3.2973, 3.3039, 3.3353, 3.4122, 3.5370]

def get_ocv(soc):
    soc = max(0.0, min(1.0, soc))
    if soc <= lut_soc[0]: return lut_ocv[0]
    if soc >= lut_soc[-1]: return lut_ocv[-1]
    for i in range(len(lut_soc)-1):
        if lut_soc[i] <= soc <= lut_soc[i+1]:
            t = (soc - lut_soc[i]) / (lut_soc[i+1] - lut_soc[i])
            return lut_ocv[i] + t * (lut_ocv[i+1] - lut_ocv[i])
    return lut_ocv[0]

def get_dOCV(soc):
    soc = max(0.0, min(1.0, soc))
    h = 0.005
    lo = max(soc - h, 0.0)
    hi = min(soc + h, 1.0)
    ds = hi - lo
    if ds < 1e-6: return 0.0
    return (get_ocv(hi) - get_ocv(lo)) / ds

print("=" * 80)
print("dOCV/dSOC at each LUT point and resulting R_dynamic")
print("=" * 80)
print(f"{'SOC':>6} {'OCV':>8} {'dOCV/dSOC':>10} {'R_old(0.0005)':>14} {'R_new proposal':>14}")
print("-" * 80)

for soc in [0.00, 0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 
            0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 1.00]:
    d = get_dOCV(soc)
    ocv = get_ocv(soc)
    r_old = 0.0005 / (abs(d) + 1e-4)
    # Proposed: scale with squared slope, clamped
    base_r = 0.001
    r_new = base_r / (d*d + 0.01)
    r_new = max(r_new, 0.0005)  # floor
    r_new = min(r_new, 5.0)     # ceiling
    print(f"{soc:6.2f} {ocv:8.4f} {d:10.4f} {r_old:14.6f} {r_new:14.6f}")

print()
print("=" * 80)
print("Key insight: At SOC 0-5%, dOCV/dSOC = 7.4, old R = 0.0000676")
print("This makes K -> 1.0, filter overshoots massively")
print()
print("At plateau SOC 20-80%, dOCV/dSOC ~ 0.02-0.3")
print("Old R = 0.0005/0.02 = 0.025 (reasonable, filter trusts CC)")
print()

# Now compute what R values actually produce stable convergent EKF
# For the 10% offset test, we want RMSE < 5%
print("=" * 80)
print("Optimal R analysis:")
print("=" * 80)
print()
print("The key is: R must NEVER be so small that K[0] > ~0.1")
print("Because a single sample correction of 10% * 3.3V = 0.33V innovation")
print("would push SoC by K[0] * 0.33 = 0.033 = 3.3% per step")
print("If K[0] = 1.0, it's a 33% push per step -> divergence")
print()

# Test different R formulas
print("Test: R = base / (|slope|^2 + eps)")
for base in [0.0005, 0.001, 0.002, 0.005]:
    for eps in [0.01, 0.05, 0.1]:
        # Test at flat region
        d_flat = 0.02
        r_flat = base / (d_flat**2 + eps)
        # Test at steep region
        d_steep = 7.4
        r_steep = base / (d_steep**2 + eps)
        print(f"  base={base:.4f}, eps={eps:.2f}: R_flat={r_flat:.4f}, R_steep={r_steep:.6f}")
