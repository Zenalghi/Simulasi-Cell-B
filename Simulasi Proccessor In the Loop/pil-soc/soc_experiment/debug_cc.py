import csv, math
rows = list(csv.DictReader(open('c:/homeesp/soc_experiment/data_logs/bms_session_20260710_144650.csv')))
Q = 20.798555 * 3600

soc_cc_ocv = 0.1456   # init dari OCV
soc_cc_jk  = 0.30     # init dari klaim JK BMS

ep = None
print("t(s)    CC_OCV  CC_JK30  JK_BMS   I(A)")
for r in rows[::500]:
    t = float(r['elapsed_s'])
    I_raw = float(r['current_A'])
    I_model = -I_raw   # balik tanda: positif=discharge di model
    if ep is not None:
        dt = t - ep
        soc_cc_ocv = max(0, min(1, soc_cc_ocv - I_model*dt/Q))
        soc_cc_jk  = max(0, min(1, soc_cc_jk  - I_model*dt/Q))
    ep = t
    soc_jk = float(r['soc_jk_pct'])
    print(f"t={t:6.0f}s  CC_OCV={soc_cc_ocv*100:5.1f}%  CC_JK30={soc_cc_jk*100:5.1f}%  JK_BMS={soc_jk:5.1f}%  I={I_raw:+.2f}A")
