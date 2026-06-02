# Diagnostic Analysis: esp.md (Old) vs esp2.md (New)

## Side-by-Side Comparison

| Dataset | CC RMSE | **Old EKF** | **New EKF** | Delta | Verdict |
|:---|:---:|:---:|:---:|:---:|:---:|
| charge_rest_60m | 8.35% | 11.99% | **45.15%** | +33.2% | CATASTROPHIC |
| DCC-4.4A | 9.66% | 9.86% | **11.44%** | +1.6% | WORSE |
| Dynamic_Profiling | 9.32% | 7.94% | **10.19%** | +2.3% | WORSE |
| charging_7.33A | 7.57% | 8.04% | **60.93%** | +52.9% | CATASTROPHIC |
| DCC_CCV_DCC (mixed) | 6.06% | 10.03% | **39.29%** | +29.3% | CATASTROPHIC |

| Dataset | **Old RMSE V** | **New RMSE V** |
|:---|:---:|:---:|
| charge_rest_60m | 11.9 mV | **142.7 mV** |
| DCC-4.4A | 3.4 mV | **38.3 mV** |
| Dynamic_Profiling | 5.0 mV | **91.3 mV** |
| charging_7.33A | 8.9 mV | **202.9 mV** |
| DCC_CCV_DCC | 7.5 mV | **98.0 mV** |

## Root Cause: Dynamic R Formula Causes Kalman Gain Explosion

The formula `R_dynamic = 0.0005 / (|dOCV/dSOC| + 1e-4)` was designed to make R large 
when the OCV curve is flat, and R small when the curve is steep.

**The problem:** At the low-SoC and high-SoC endpoints, `dOCV/dSOC` is VERY steep 
(e.g., ~7.4 V/unit at SOC 0-5%, ~2.5 V/unit at 90-100%). This drives R_dynamic to 
absurdly small values:

- At SOC=2%: dOCV/dSOC ≈ 7.4 → R = 0.0005/7.4 = 0.0000676 (too small!)
- At SOC=50%: dOCV/dSOC ≈ 0.02 → R = 0.0005/0.02 = 0.025 (reasonable)
- At SOC=95%: dOCV/dSOC ≈ 2.5 → R = 0.0005/2.5 = 0.0002 (too small!)

When R is tiny, the Kalman gain K approaches 1.0 — the filter blindly follows the 
voltage measurement. Any model mismatch (ECM error, R0 lookup error) gets amplified 
directly into the SoC estimate, causing massive overshoot.

The charge and charging datasets start at very low SoC (0% and 6%), exactly where 
dOCV/dSOC is steepest. The filter immediately overshoots on the first few samples and 
never recovers.

## Fix Strategy

1. **Clamp R_dynamic** with a floor and ceiling to prevent extreme values
2. **Use a proper scaling** that transitions smoothly between "trust voltage" and 
   "trust CC" without allowing K to explode
3. **Tune base_R** to work with the actual sensor noise level (~2-5 mV^2)
