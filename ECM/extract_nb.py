import json
with open(r'c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\ECM\ecm_ekf_final_v4-csv_FIX.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)
with open(r'c:\Users\zenaj\Documents\Courses\Sms 8\Simulasi-Cell-B\ECM\nb_dump.txt', 'w', encoding='utf-8') as out:
    for i, cell in enumerate(nb['cells']):
        out.write(f"--- CELL {i} ({cell['cell_type']}) ---\n")
        out.write("".join(cell['source']) + "\n")
