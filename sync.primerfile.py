# primer_formatter_auto_with_settings.py

import pandas as pd
from tkinter import messagebox, Tk, filedialog, Label, Button, Entry, Toplevel, StringVar, colorchooser, Frame, PhotoImage
import os
import json
import tempfile
import shutil
import base64
from PIL import Image, ImageTk
import io


CONFIG_FILE = "Settings.json"
GEAR_ICON_PATH = "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"
DEFAULT_CONFIG = {
    "input_path": "",
    "output_path": "",
    "color1": "#00ffff",
    "color2": "#008000"
}



def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def extract_primer_text_format(file_path: str, color1: str, color2: str) -> list:
    safe_path = os.path.normpath(file_path)
    try:
        df = pd.read_excel(safe_path, header=None)
    except Exception as e:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            shutil.copyfile(safe_path, tmp.name)
            df = pd.read_excel(tmp.name, header=None)

    primers = []
    for _, row in df.iterrows():
        name = row[0]
        seq = row[1]
        if pd.notna(name) and pd.notna(seq):
            line = f"{name}\t{seq}\tprimer_bind\t{color1}\t{color2}"
            primers.append((name, line))
    return primers

def load_existing_primers(output_file: str) -> set:
    if not os.path.exists(output_file):
        return set()
    with open(output_file, 'r') as f:
        return set(line.split("\t")[0] for line in f if line.strip())

def save_primer_text(primers: list, output_file: str):
    with open(output_file, 'w') as f:
        f.write("\n".join(line for _, line in primers))

def run_formatter(config, root):
    try:
        input_path = config["input_path"]
        output_path = config["output_path"]
        color1 = config.get("color1", "#00ffff")
        color2 = config.get("color2", "#008000")

        if not input_path or not output_path:
            messagebox.showwarning("設定が必要", "入力ファイルまたは出力ファイルのパスが設定されていません。⚙から設定してください。")
            return

        new_primers = extract_primer_text_format(input_path, color1, color2)
        existing_names = load_existing_primers(output_path)

        added_names = [name for name, _ in new_primers if name not in existing_names]
        save_primer_text(new_primers, output_path)

        if added_names:
            added_text = "追加されたプライマー:\n" + "\n".join(added_names)
        else:
            added_text = "新たなプライマーは見つかりませんでした"

        messagebox.showinfo(
            "成功",
            f"{len(new_primers)}個のプライマーを読み込みました:\n{output_path}\n\n{added_text}"
        )
    except Exception as e:
        err_msg = str(e)
        if "Invalid argument" in err_msg:
            err_msg += "\n\n→ Googleドライブや特殊フォルダのファイルはエラーになることがあります。\n通常のローカルフォルダにコピーしてから実行してください。"
        messagebox.showerror("エラー", err_msg)

def set_paths(config):
    def choose_input():
        path = filedialog.askopenfilename()
        if path:
            input_var.set(path)

    def choose_output():
        path = filedialog.asksaveasfilename()
        if path:
            output_var.set(path)

    def choose_color(var, preview):
        current = var.get()
        color = colorchooser.askcolor(color=current)
        if color[1]:
            var.set(color[1])
            preview.config(bg=color[1])

    def save_and_close():
        config["input_path"] = input_var.get()
        config["output_path"] = output_var.get()
        config["color1"] = color1_var.get()
        config["color2"] = color2_var.get()
        save_config(config)
        settings_window.destroy()
        run_formatter(config, root)

    settings_window = Toplevel()
    settings_window.title("パスと色の設定")
    settings_window.geometry("600x250")

    input_var = StringVar(value=config.get("input_path", ""))
    output_var = StringVar(value=config.get("output_path", ""))
    color1_var = StringVar(value=config.get("color1", "#00ffff"))
    color2_var = StringVar(value=config.get("color2", "#008000"))

    Label(settings_window, text="入力ファイル:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
    Entry(settings_window, textvariable=input_var, width=50).grid(row=0, column=1, padx=5, pady=5)
    Button(settings_window, text="選択", command=choose_input).grid(row=0, column=2, padx=5, pady=5)

    Label(settings_window, text="出力ファイル:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
    Entry(settings_window, textvariable=output_var, width=50).grid(row=1, column=1, padx=5, pady=5)
    Button(settings_window, text="選択", command=choose_output).grid(row=1, column=2, padx=5, pady=5)

    Label(settings_window, text="Fwd Primer Color:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
    preview1 = Frame(settings_window, width=20, height=20, bg=color1_var.get(), relief='solid', bd=1)
    preview1.grid(row=2, column=1, sticky='w')
    Entry(settings_window, textvariable=color1_var, width=10).grid(row=2, column=1, padx=(30, 0), sticky='w')
    Button(settings_window, text="色選択", command=lambda: choose_color(color1_var, preview1)).grid(row=2, column=2, padx=5, pady=5)

    Label(settings_window, text="Rev Primer Color:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
    preview2 = Frame(settings_window, width=20, height=20, bg=color2_var.get(), relief='solid', bd=1)
    preview2.grid(row=3, column=1, sticky='w')
    Entry(settings_window, textvariable=color2_var, width=10).grid(row=3, column=1, padx=(30, 0), sticky='w')
    Button(settings_window, text="色選択", command=lambda: choose_color(color2_var, preview2)).grid(row=3, column=2, padx=5, pady=5)

    Button(settings_window, text="保存", command=save_and_close).grid(row=4, column=1, pady=10)

def main():
        global root
        config = load_config()
        root = Tk()
        root.title("Primer Library Sync")
        root.geometry("120x120")

        run_formatter(config, root)

        # --- Pillowでbase64画像を正しく表示する ---
        image_data = base64.b64decode(GEAR_ICON_PATH)
        pil_image = Image.open(io.BytesIO(image_data)).resize((48, 48))  # ←サイズ調整（例: 48×48）
        gear_img = ImageTk.PhotoImage(pil_image)

        gear_button = Button(
            root,
            image=gear_img,
            command=lambda: set_paths(config),
            borderwidth=0,
            highlightthickness=0,
            bg="white",
            activebackground="white"
        )
        gear_button.image = gear_img
        gear_button.pack(pady=20)

        root.mainloop()

if __name__ == "__main__":
    main()