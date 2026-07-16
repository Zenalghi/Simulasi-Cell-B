import pandas as pd
import numpy as np
import os
from scipy.optimize import curve_fit

# Load data
f_dcc = "DCC 4.4A, 2.5V - CCV 6.6, 3.65V - DCC 4.4A, 2.5V.csv"
f_hppc = "hppc (loop10x).csv"

# Preprocess function (from CELL 9)
def preprocess(f):
    with open(f, 'r') as file:
        lines = file.readlines()
        header_idx = next(i for i, line in enumerate(lines) if line.startswith('Time(S)'))
    df = pd.read_csv(f, skiprows=header_idx)
    df = df.rename(columns={'Time(S)': 'Time (s)', 'Cur(A)': 'Current (A)', 'Vol(V)': 'Voltage (V)'})
    
    df_clean = df.drop_duplicates(subset=['Time (s)'], keep='first').copy()
    df_clean = df_clean.set_index('Time (s)')
    
    t_min = int(df_clean.index.min())
    t_max = int(df_clean.index.max())
    uniform_time_index = np.arange(t_min, t_max + 1, 1)
    
    df_clean = df_clean.reindex(uniform_time_index)
    df_clean = df_clean.interpolate(method='linear')
    df_clean = df_clean.reset_index().rename(columns={'index': 'Time (s)'})
    return df_clean

df_full = preprocess(f_dcc)
df_hppc = preprocess(f_hppc)

# Cell 11: Capacity Analysis
df_full['is_active'] = (df_full['Current (A)'] > 0.1).astype(int)
df_full['phase_change'] = df_full['is_active'].diff().fillna(0)
start_idx = df_full[df_full['phase_change'] == 1].index.tolist()
end_idx = df_full[df_full['phase_change'] == -1].index.tolist()
if df_full['is_active'].iloc[-1] == 1: 
    end_idx.append(df_full.index[-1])

Q_capacity_Ah = 0.0
Q_capacity_As = 0.0
for i, (s, e) in enumerate(zip(start_idx, end_idx)):
    v_start = df_full.loc[s:s+10, 'Voltage (V)'].mean()
    v_end = df_full.loc[e-10:e, 'Voltage (V)'].mean()
    phase_cap_As = df_full.loc[s:e, 'Current (A)'].sum()
    phase_cap_Ah = phase_cap_As / 3600.0
    if v_end < v_start: 
        if phase_cap_Ah > Q_capacity_Ah:
            Q_capacity_Ah = phase_cap_Ah
            Q_capacity_As = phase_cap_As

# Cell 15: HPPC Ah tracking
Q_Ah_nominal = Q_capacity_Ah
df_hppc['dt_s'] = df_hppc['Time (s)'].diff().fillna(0.0)
df_hppc['Ah_cumulative'] = (df_hppc['Current (A)'] * df_hppc['dt_s']).cumsum() / 3600.0

# Cell 24: Detect HPPC pulses
df_hppc['is_pulse'] = (df_hppc['Current (A)'] > 0.1).astype(int)
df_hppc['pulse_change'] = df_hppc['is_pulse'].diff().fillna(0)
pulse_starts = df_hppc[df_hppc['pulse_change'] == 1].index.tolist()
pulse_ends = df_hppc[df_hppc['pulse_change'] == -1].index.tolist()
if df_hppc['is_pulse'].iloc[0] == 1: pulse_starts.insert(0, 0)
if df_hppc['is_pulse'].iloc[-1] == 1: pulse_ends.append(len(df_hppc)-1)

# Cell 25: ECM Parameters Extraction
def relax_model(t, v_inf, A, tau):
    return v_inf - A * np.exp(-t / tau)

ecm_parameters = []
for i in range(1, len(pulse_starts), 2):
    s_idx = pulse_starts[i]
    e_idx = pulse_ends[i]
    
    I_pulse = df_hppc.loc[e_idx - 2, 'Current (A)']
    V_under_load = df_hppc.loc[e_idx - 2, 'Voltage (V)']
    V_instant_rest = df_hppc.loc[e_idx, 'Voltage (V)']
    
    R0_ohms = (V_instant_rest - V_under_load) / I_pulse
    
    end_rest_idx = pulse_starts[i+1] if (i+1 < len(pulse_starts)) else df_hppc.index[-1]
    
    t_fit = df_hppc.loc[e_idx:end_rest_idx, 'Time (s)'].values
    v_fit = df_hppc.loc[e_idx:end_rest_idx, 'Voltage (V)'].values
    
    t_rel = t_fit - t_fit[0]
    
    try:
        popt, _ = curve_fit(relax_model, t_rel, v_fit, p0=[v_fit[-1], 0.05, 50], maxfev=5000)
        A_polarization = popt[1]
        tau_rc = popt[2]
        
        R1_ohms = A_polarization / I_pulse
        C1_farads = tau_rc / R1_ohms
        
        ah_discharged = df_hppc.loc[e_idx, 'Ah_cumulative']
        soc_terkini = 1.0 - (ah_discharged / Q_Ah_nominal)
        soc_terkini = max(0.0, soc_terkini)
        
        # M and M0 are 0 because this is a 1-RC without hysteresis model
        M_factor = 0.0
        M0_factor = 0.0
        
        ecm_parameters.append([soc_terkini * 100, R0_ohms, M_factor, M0_factor, R1_ohms, C1_farads, tau_rc])
    except RuntimeError:
        pass

df_ecm = pd.DataFrame(ecm_parameters, columns=['SOC (%)', 'R0 (Ohm)', 'M', 'M0', 'R (Ohm)', 'C (Farad)', 'RC (Tau)'])
df_ecm = df_ecm.sort_values(by='SOC (%)', ascending=False).reset_index(drop=True)

# Format
df_ecm['SOC (%)'] = df_ecm['SOC (%)'].apply(lambda x: f"{x:.2f}")
df_ecm['R0 (Ohm)'] = df_ecm['R0 (Ohm)'].apply(lambda x: f"{x:.6f}")
df_ecm['M'] = "N/A"
df_ecm['M0'] = "N/A"
df_ecm['R (Ohm)'] = df_ecm['R (Ohm)'].apply(lambda x: f"{x:.6f}")
df_ecm['C (Farad)'] = df_ecm['C (Farad)'].apply(lambda x: f"{x:.2f}")
df_ecm['RC (Tau)'] = df_ecm['RC (Tau)'].apply(lambda x: f"{x:.2f}")

out_path = r"c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\ECM\hasil_parameter_hppc.csv"
df_ecm.to_csv(out_path, index=False)
print("Updated report model written to:", out_path)
