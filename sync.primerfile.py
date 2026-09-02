import json
import os
import shutil
import tempfile
from pathlib import Path
from tkinter import (
    Button,
    Entry,
    Frame,
    Label,
    StringVar,
    Tk,
    Toplevel,
    colorchooser,
    filedialog,
    messagebox,
)

import pandas as pd


CONFIG_FILE = Path(__file__).with_name("Settings.json")
DEFAULT_COLOR1 = "#00ffff"
DEFAULT_COLOR2 = "#008000"
DEFAULT_CONFIG = {"libraries": []}


def load_config():
    if not CONFIG_FILE.exists():
        return {"libraries": []}

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        messagebox.showwarning(
            "設定の読み込みエラー",
            f"Settings.jsonを読み込めませんでした。初期設定で起動します。\n\n{exc}",
        )
        return {"libraries": []}

    # 旧版（1ライブラリ形式）の設定を自動移行する。
    if "libraries" not in config:
        old_library = {
            "input_path": config.get("input_path", ""),
            "output_path": config.get("output_path", ""),
            "color1": config.get("color1", DEFAULT_COLOR1),
            "color2": config.get("color2", DEFAULT_COLOR2),
        }
        config = {"libraries": [old_library] if any(old_library.values()) else []}

    return config


def save_config(config):
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def read_excel(file_path):
    safe_path = os.path.normpath(file_path)
    try:
        return pd.read_excel(safe_path, header=None)
    except Exception:
        # 同期フォルダ等で直接読めない場合は一時ファイル経由で再試行する。
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe_path).suffix) as tmp:
                temp_path = tmp.name
            shutil.copyfile(safe_path, temp_path)
            return pd.read_excel(temp_path, header=None)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)


def extract_primer_lines(file_path, color1, color2):
    df = read_excel(file_path)
    if df.shape[1] < 2:
        raise ValueError("入力Excelには、名前と配列の2列が必要です。")

    primers = []
    for row_number, row in df.iterrows():
        name, sequence = row.iloc[0], row.iloc[1]
        if pd.isna(name) or pd.isna(sequence):
            continue

        name = str(name).strip()
        # 配列中の空白と改行を除去し、すべて小文字に統一する。
        sequence = "".join(str(sequence).split()).lower()
        if not name or not sequence:
            continue
        primers.append((name, sequence, f"{name}\t{sequence}\tprimer_bind\t{color1}\t{color2}"))

    return primers


def read_existing_text(output_path):
    try:
        return Path(output_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def describe_changes(old_text, new_primers):
    old_items = {}
    if old_text is not None:
        for line in old_text.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2:
                old_items[fields[0]] = fields[1]

    new_items = {name: sequence for name, sequence, _ in new_primers}
    added = [name for name in new_items if name not in old_items]
    changed = [name for name in new_items if name in old_items and new_items[name] != old_items[name]]
    removed = [name for name in old_items if name not in new_items]
    return added, changed, removed


def write_if_changed(primers, output_path):
    # 末尾改行も含めて常に同じ形式で比較する。
    new_text = "\n".join(line for _, _, line in primers)
    if new_text:
        new_text += "\n"

    old_text = read_existing_text(output_path)
    # 末尾改行の有無だけでは更新しない。各レコードの実内容が同じなら保存を省略する。
    if old_text is not None and old_text.splitlines() == new_text.splitlines():
        return False, ([], [], [])

    changes = describe_changes(old_text, primers)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # 同じフォルダの一時ファイルへ書いてから置換し、途中終了による破損を防ぐ。
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(new_text)
        os.replace(temp_name, destination)
    except Exception:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise

    return True, changes


def update_library(library):
    input_path = library.get("input_path", "").strip()
    output_path = library.get("output_path", "").strip()
    if not input_path or not output_path:
        raise ValueError("入力ファイルまたは出力ファイルが未設定です。")

    primers = extract_primer_lines(
        input_path,
        library.get("color1", DEFAULT_COLOR1),
        library.get("color2", DEFAULT_COLOR2),
    )
    updated, changes = write_if_changed(primers, output_path)
    return updated, len(primers), changes


def run_formatter(config):
    libraries = config.get("libraries", [])
    if not libraries:
        messagebox.showwarning("設定が必要", "ライブラリがありません。⚙ 設定から追加してください。")
        return

    reports = []
    errors = []
    for index, library in enumerate(libraries, start=1):
        label = Path(library.get("output_path", "")).name or f"ライブラリ {index}"
        try:
            updated, count, (added, changed, removed) = update_library(library)
            if updated:
                details = []
                if added:
                    details.append(f"追加 {len(added)}")
                if changed:
                    details.append(f"配列変更 {len(changed)}")
                if removed:
                    details.append(f"削除 {len(removed)}")
                reports.append(f"{label}: 更新（{count}件、{', '.join(details) or '書式変更'}）")
            else:
                reports.append(f"{label}: 変更なし（{count}件）")
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    message = "\n".join(reports)
    if errors:
        messagebox.showerror("一部エラー", f"{message}\n\nエラー:\n" + "\n".join(errors))
    else:
        messagebox.showinfo("更新結果", message)


def settings_dialog(config, root):
    window = Toplevel(root)
    window.title("ライブラリ設定")
    window.geometry("850x420")
    rows_frame = Frame(window)
    rows_frame.pack(fill="both", expand=True, padx=10, pady=10)
    row_widgets = []

    for column, text in enumerate(("入力Excel", "出力ライブラリ", "Fwd色", "Rev色", "")):
        Label(rows_frame, text=text).grid(row=0, column=column, padx=3, pady=3)

    def choose_file(variable, save=False):
        path = filedialog.asksaveasfilename() if save else filedialog.askopenfilename(
            filetypes=[("Excel", "*.xlsx *.xls"), ("すべて", "*.*")]
        )
        if path:
            variable.set(path)

    def choose_color(variable, button):
        selected = colorchooser.askcolor(color=variable.get())[1]
        if selected:
            variable.set(selected)
            button.config(bg=selected, activebackground=selected)

    def add_row(values=None):
        values = values or {}
        row = len(row_widgets) + 1
        input_var = StringVar(value=values.get("input_path", ""))
        output_var = StringVar(value=values.get("output_path", ""))
        color1_var = StringVar(value=values.get("color1", DEFAULT_COLOR1))
        color2_var = StringVar(value=values.get("color2", DEFAULT_COLOR2))

        input_entry = Entry(rows_frame, textvariable=input_var, width=30)
        input_entry.grid(row=row, column=0, padx=3, pady=3)
        output_entry = Entry(rows_frame, textvariable=output_var, width=30)
        output_entry.grid(row=row, column=1, padx=3, pady=3)
        color1_button = Button(rows_frame, textvariable=color1_var, width=9, bg=color1_var.get())
        color1_button.config(command=lambda: choose_color(color1_var, color1_button))
        color1_button.grid(row=row, column=2, padx=3)
        color2_button = Button(rows_frame, textvariable=color2_var, width=9, bg=color2_var.get())
        color2_button.config(command=lambda: choose_color(color2_var, color2_button))
        color2_button.grid(row=row, column=3, padx=3)

        widgets = [input_entry, output_entry, color1_button, color2_button]
        record = (input_var, output_var, color1_var, color2_var, widgets)
        row_widgets.append(record)

        input_entry.bind("<Double-Button-1>", lambda _event: choose_file(input_var))
        output_entry.bind("<Double-Button-1>", lambda _event: choose_file(output_var, save=True))

        remove_button = Button(rows_frame, text="削除", command=lambda: remove_row(record, remove_button))
        remove_button.grid(row=row, column=4, padx=3)
        widgets.append(remove_button)

    def remove_row(record, _button):
        for widget in record[4]:
            widget.destroy()
        row_widgets.remove(record)
        for row, current in enumerate(row_widgets, start=1):
            for column, widget in enumerate(current[4]):
                widget.grid_configure(row=row, column=column)

    def save_and_close():
        libraries = []
        for input_var, output_var, color1_var, color2_var, _ in row_widgets:
            if not input_var.get().strip() and not output_var.get().strip():
                continue
            libraries.append({
                "input_path": input_var.get().strip(),
                "output_path": output_var.get().strip(),
                "color1": color1_var.get(),
                "color2": color2_var.get(),
            })
        config["libraries"] = libraries
        save_config(config)
        window.destroy()
        run_formatter(config)

    for library in config.get("libraries", []):
        add_row(library)
    if not row_widgets:
        add_row()

    controls = Frame(window)
    controls.pack(fill="x", padx=10, pady=(0, 10))
    Button(controls, text="＋ ライブラリ追加", command=add_row).pack(side="left")
    Button(controls, text="保存して更新", command=save_and_close).pack(side="right")
    Label(controls, text="パス欄をダブルクリックするとファイルを選択できます。", fg="#555555").pack(side="left", padx=15)


def main():
    root = Tk()
    root.title("Primer Library Sync")
    root.geometry("250x130")
    config = load_config()

    Button(root, text="すべて更新", width=20, command=lambda: run_formatter(config)).pack(pady=(18, 7))
    Button(root, text="⚙ ライブラリ設定", width=20, command=lambda: settings_dialog(config, root)).pack()

    # 画面を表示した直後に、登録済みの全ライブラリを自動確認・更新する。
    # afterを使うことで、起動処理中ではなくTkのイベント開始後に実行する。
    root.after(100, lambda: run_formatter(config))
    root.mainloop()


if __name__ == "__main__":
    main()
