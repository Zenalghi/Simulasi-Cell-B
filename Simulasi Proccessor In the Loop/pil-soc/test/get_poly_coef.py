import numpy as np

# Data OCV dari ekstraksi Anda
soc_data = np.array([
    0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 
    0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0
])

ocv_data = np.array([
    2.655, 3.026, 3.196, 3.239, 3.226, 3.224, 3.242, 3.262, 3.275, 
    3.283, 3.287, 3.288, 3.288, 3.288, 3.291, 3.296, 3.297, 3.303, 
    3.331, 3.402, 3.537
])

# Melakukan Polynomial Fitting Orde 6
# numpy.polyfit mengembalikan dari pangkat tertinggi ke terendah (p6, p5 ... p0)
coefs_high_to_low = np.polyfit(soc_data, ocv_data, 6)

# Kita balik urutannya agar sesuai dengan rumus di C++ (p0, p1 ... p6)
coefs_low_to_high = coefs_high_to_low[::-1]

print("=== COPY ARRAY INI KE DALAM main.cpp ESP32 ===")
print("const float P_COEF[7] = {")
for i, coef in enumerate(coefs_low_to_high):
    comma = "," if i < 6 else ""
    print(f"    {coef:.6f}{comma} // p{i}")
print("};")
print("==============================================")