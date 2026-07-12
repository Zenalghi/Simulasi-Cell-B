import csv
import matplotlib.pyplot as plt
import os
import sys

def plot_v_a(csv_file):
    if not os.path.exists(csv_file):
        print(f"Error: File {csv_file} tidak ditemukan.")
        sys.exit(1)

    times = []
    voltages = []
    currents = []
    
    # Baca data dari CSV
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            times.append(float(row['elapsed_s']) / 60.0) # Ubah ke menit agar lebih mudah dibaca
            voltages.append(float(row['voltage_V']))
            currents.append(float(row['current_A']))

    # Setup figure dengan background putih
    fig, ax1 = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('white')
    ax1.set_facecolor('white')

    # Plot Tegangan (Biru)
    ax1.set_xlabel('Waktu (menit)', fontsize=12)
    ax1.set_ylabel('Tegangan (V)', color='blue', fontsize=12)
    ax1.plot(times, voltages, color='blue', label='Tegangan (V)', linewidth=1.5)
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.grid(True, alpha=0.3)

    # Buat sumbu Y kedua untuk Arus
    ax2 = ax1.twinx()
    
    # Plot Arus (Merah)
    ax2.set_ylabel('Arus (A)', color='red', fontsize=12)
    ax2.plot(times, currents, color='red', label='Arus (A)', linewidth=1.5, alpha=0.8)
    ax2.tick_params(axis='y', labelcolor='red')

    # Judul
    plt.title(f'Tegangan dan Arus terhadap Waktu\nFile: {os.path.basename(csv_file)}', fontsize=14, fontweight='bold')
    
    # Simpan hasil
    fig.tight_layout()
    out_path = os.path.splitext(csv_file)[0] + "_plot_v_a.png"
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
    print(f"[OK] Grafik berhasil disimpan di: {out_path}")

if __name__ == "__main__":
    # Secara default menggunakan file yang Anda minta
    target_file = r"c:\homeesp\soc_experiment\data_logs\bms_jikong_soc30-60pct.csv"
    
    # Bisa juga menerima argumen dari terminal jika ingin pakai file lain
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        
    plot_v_a(target_file)
