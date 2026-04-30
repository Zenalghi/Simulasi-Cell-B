import pandas as pd
import json
import time
import paho.mqtt.client as mqtt

# =========================================================
# 1. KONFIGURASI MQTT
# =========================================================
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
TOPIC_INJECT = "bms_panel/2602165/data/main" # Sesuaikan dengan topik C++

client = mqtt.Client(client_id="Laptop_Injector")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# =========================================================
# 2. MENU PEMILIHAN DATASET
# =========================================================
print("=== MENU SIMULASI HiL BMS ===")
print("1. Pengisian Daya (charge-rest 60m.csv)")
print("2. Pengosongan Konstan (DCC 4.4A...csv)")
print("3. Pembebanan Dinamis Urban Load (Dynamic Profiling.csv)")
pilihan = input("Pilih dataset (1/2/3): ")

if pilihan == '1':
    file_path = "charge-rest 60m.csv"
elif pilihan == '2':
    file_path = "DCC 4.4A, 2.5V - CCV 6.6, 3.65V - DCC 4.4A, 2.5V.csv"
elif pilihan == '3':
    file_path = "Dynamic Profiling (Urban Load).csv"
else:
    print("Pilihan tidak valid!")
    exit()

print(f"\nMemuat dataset: {file_path}")
try:
    df = pd.read_csv(file_path)
except FileNotFoundError:
    print("Error: File CSV tidak ditemukan di folder yang sama!")
    exit()

# PASTIKAN NAMA KOLOM SESUAI DENGAN FORMAT ZKETECH
# Biasanya: 'Voltage(V)', 'Current(A)', 'Capacity(Ah)'
# Silakan ubah string di bawah jika nama kolomnya beda
col_v = 'Voltage' 
col_i = 'Current'

print("Memulai Injeksi Data ke ESP32 dalam 3 detik...")
time.sleep(3)

# =========================================================
# 3. LOOP INJEKSI DATA (SIMULASI WAKTU NYATA)
# =========================================================
for index, row in df.iterrows():
    # ZKETECH menganggap discharge positif, charge negatif. 
    # Pastikan orientasinya sama dengan logika Coulomb Counting ESP32 mu.
    v_meas = float(row[col_v])
    i_meas = float(row[col_i]) 
    
    # TRICK: Karena kode ESP32 menghitung avg_cell_v dari 8 sel,
    # kita kirim tegangan 1S zketech ini ke semua 8 array sel.
    cells_array = [v_meas] * 8
    
    payload = {
        "voltage": v_meas, # Anggap sistem 1S
        "current": i_meas,
        "power": v_meas * i_meas,
        "mos_temp": 30.0,  # Dummy suhu
        "bat_temp1": 26.0, # Dummy suhu
        "bat_temp2": 26.5, # Dummy suhu
        "cells_v": cells_array,
        "wire_res": [0.0] * 8
    }
    
    # Kirim ke ESP32
    client.publish(TOPIC_INJECT, json.dumps(payload))
    print(f"Step {index}: Injected V={v_meas:.3f}V, I={i_meas:.2f}A")
    
    # Delay 1 detik untuk menyimulasikan waktu nyata (sesuai dt=1.0 di ESP32)
    time.sleep(1) 

print("Simulasi Selesai!")
client.loop_stop()