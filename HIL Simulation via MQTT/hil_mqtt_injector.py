import pandas as pd
import json
import time
import paho.mqtt.client as mqtt
import os

# =========================================================
# 1. KONFIGURASI MQTT BROKER UMUM
# =========================================================
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883

# =========================================================
# 2. MENU PEMILIHAN DATASET & SKENARIO
# =========================================================
print("=== MENU SIMULASI HiL BMS ===")
print("1. Pengisian Daya (charge-rest 60m.csv)")
print("2. Pengosongan Konstan (DCC 4.4A...csv)")
print("3. Pembebanan Dinamis Urban Load (Dynamic Profiling.csv)")
pilihan = input("Pilih dataset (1/2/3): ")

# Inisialisasi variabel berdasarkan pilihan
if pilihan == '1':
    file_path = r"HIL Simulation via MQTT\charge-rest 60m.csv"
    TOPIC_INJECT = "bms_panel/2602165/data/main"
    CLIENT_ID = "Laptop_Injector"
elif pilihan == '2':
    file_path = r"HIL Simulation via MQTT\DCC 4.4A, 2.5V.csv"
    TOPIC_INJECT = "batteryss/54673/data/main"
    CLIENT_ID = "Laptop2-injector"
elif pilihan == '3':
    file_path = r"HIL Simulation via MQTT\Dynamic Profiling (Urban Load).csv"
    TOPIC_INJECT = "bms_panel/2602165/data/main"
    CLIENT_ID = "Laptop3-injector"
else:
    print("Pilihan tidak valid!")
    exit()

print(f"\nMemuat dataset: {file_path}")
print(f"Menggunakan Client ID: {CLIENT_ID}")
print(f"Target Topik MQTT: {TOPIC_INJECT}")

# =========================================================
# 3. KONEKSI MQTT (Dilakukan setelah skenario dipilih)
# =========================================================
try:
    client = mqtt.Client(client_id=CLIENT_ID)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    print("Berhasil terhubung ke Broker MQTT.")
except Exception as e:
    print(f"Gagal terhubung ke Broker MQTT: {e}")
    exit()

# Cek apakah file benar-benar ada
if not os.path.exists(file_path):
    print(f"Error: File CSV tidak ditemukan! Pastikan path folder benar.")
    client.loop_stop()
    exit()

# =========================================================
# 4. AUTO-SKIP ZKETECH METADATA
# =========================================================
# Kita cari baris ke berapa yang mengandung "Time(S),Cur(A),Vol(V)"
header_row = 0
with open(file_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if "Time(S)" in line and "Vol(V)" in line:
            header_row = i
            break

print(f"Header tabel ditemukan pada baris ke-{header_row + 1}. Melewati baris metadata...")

# Membaca CSV dengan melewati baris metadata
try:
    df = pd.read_csv(file_path, skiprows=header_row)
except Exception as e:
    print(f"Gagal membaca CSV: {e}")
    client.loop_stop()
    exit()

# Menyesuaikan nama kolom dengan format ZKETECH
col_v = 'Vol(V)' 
col_i = 'Cur(A)'

print("Memulai Injeksi Data ke ESP32 dalam 3 detik...")
time.sleep(3)

# =========================================================
# 5. LOOP INJEKSI DATA (SIMULASI WAKTU NYATA)
# =========================================================
for index, row in df.iterrows():
    v_meas = float(row[col_v])
    i_meas = float(row[col_i]) 
    
    # --- KOREKSI ORIENTASI ARUS (SANGAT PENTING) ---
    # Di ZKETECH, arus selalu dicatat Positif (baik charge maupun discharge).
    # Di rumus ESP32 Anda: SOC = SOC - (I * dt). 
    # Artinya Arus Positif = Discharge, Arus Negatif = Charge.
    if pilihan == '1':
        # Mode Charge: Kita paksakan arusnya menjadi negatif agar SOC di ESP32 bertambah
        i_meas = -abs(i_meas)
    else:
        # Mode Discharge: Arusnya dibiarkan positif agar SOC di ESP32 berkurang
        i_meas = abs(i_meas)
    
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
    print(f"[{CLIENT_ID}] Step {index}: Injected V={v_meas:.3f}V, I={i_meas:.2f}A")
    
    # Delay 1 detik untuk menyimulasikan waktu nyata (sesuai dt=1.0 di ESP32)
    time.sleep(1) 

print("Simulasi Selesai!")
client.loop_stop()