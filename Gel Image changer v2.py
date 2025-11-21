import os
import tkinter as tk
from tkinter import filedialog
import numpy as np
import cv2
from PIL import Image, ImageTk

# ---- ドラッグ＆ドロップ対応 ----
# as
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False
    TkinterDnD = None
    DND_FILES = None


def make_root():
    """TkinterDnD対応のrootを生成"""
    if HAS_DND and TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except Exception:
            pass
    return tk.Tk()


class GelImageProcessor:
    def __init__(self, root):
        self.root = root
        self.file_path = None
        self.image = None
        self.corrected_image = None
        self.displayed_image = None

        self.scale_x = 1.0
        self.scale_y = 1.0
        self.auto_rect_xywh = None

        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.save_dpi = 300
        self.base_image_for_rotation = None
        self.manual_angle_var = tk.DoubleVar(value=0.0)

        self.create_ui()

    # ---------------- UI ---------------- #
    def create_ui(self):
        self.root.title("ゲル画像処理ツール")

        # メニュー（DPI設定）
        menubar = tk.Menu(self.root)
        menu_settings = tk.Menu(menubar, tearoff=0)
        menu_settings.add_command(label="DPI設定を変更", command=self.change_dpi)
        menubar.add_cascade(label="設定", menu=menu_settings)
        self.root.config(menu=menubar)

        

        # ツールバー
        toolbar = tk.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=6, pady=6)
        tk.Button(toolbar, text="画像を選択", command=self.select_file).pack(side="left", padx=3)
        tk.Button(toolbar, text="自動処理（ゲル認識→切り取り→回転）", command=self.process_image).pack(side="left", padx=3)
        tk.Button(toolbar, text="保存", command=self.export_corrected_image).pack(side="right", padx=3)
        tk.Button(toolbar, text="リセット（元画像に戻す）", command=self.reset_to_original).pack(side="left", padx=3)


        # ステータス表示
        self.status_label = tk.Label(self.root, text="ステータス: 待機中", fg="blue", anchor="w")
        self.status_label.pack(fill="x", padx=8, pady=2)

        # キャンバス（D&D対応部分）
        self.canvas = tk.Canvas(self.root, bg="#333333")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_resize)

        self.show_placeholder_text()

        # 手動トリミング（ドラッグで矩形）
        self.canvas.bind("<Button-1>", self.start_crop)
        self.canvas.bind("<B1-Motion>", self.draw_crop_rect)
        self.canvas.bind("<ButtonRelease-1>", self.finish_crop)

        # ---- D&D登録（キャンバスのみ）----
        if HAS_DND:
            try:
                self.canvas.drop_target_register(DND_FILES)
                self.canvas.dnd_bind('<<Drop>>', self.on_drop)
                self.update_status("ドラッグ＆ドロップが有効です（キャンバス内）。")
            except Exception:
                self.update_status("D&D登録に失敗しました（tkinterdnd2が正しくインストールされていません）", "red")

        # 下部：手動回転フェーダー
        rot_frame = tk.Frame(self.root)
        rot_frame.pack(side="bottom", fill="x", padx=8, pady=6)
        tk.Label(rot_frame, text="手動回転 (°)：").pack(side="left")
        self.rot_scale = tk.Scale(
            rot_frame, from_=-30.0, to=30.0, resolution=0.001,
            orient=tk.HORIZONTAL, variable=self.manual_angle_var,
            length=420, command=self.on_rotate_preview
        )
        self.rot_scale.pack(side="left", padx=6)
        self.angle_entry = tk.Entry(rot_frame, width=12)
        self.angle_entry.insert(0, "0.000")
        self.angle_entry.pack(side="left")
        tk.Button(rot_frame, text="適用", command=self.apply_angle_from_entry).pack(side="left", padx=4)
        tk.Button(rot_frame, text="確定", command=self.confirm_rotation).pack(side="left", padx=8)
        tk.Button(rot_frame, text="リセット", command=self.reset_rotation_controls).pack(side="left")

    def update_status(self, message, color="blue"):
        self.status_label.config(text=f"ステータス: {message}", fg=color)

    def reset_to_original(self):
        """読み込んだ元画像に戻す"""
        if self.image is None:
            self.update_status("画像が読み込まれていません。", "red")
            return

        self.corrected_image = None
        self.displayed_image = None
        self.base_image_for_rotation = None
        self.auto_rect_xywh = None
        self.reset_rotation_controls()
        self.display_image(self.image)
        self.update_status("元画像に戻しました。")



    # ---------------- D&Dイベント処理 ---------------- #
    def on_drop(self, event):
        """キャンバス内にドロップされた画像を読み込む（どんな形式でも対応）"""
        raw = event.data.strip()

        # --- file:/// 形式のとき ---
        if raw.startswith("file:///"):
            raw = raw.replace("file:///", "")
            raw = raw.replace("/", "\\")  # Windowsパスに変換

        # --- {C:\path with spaces\file.tif} 形式のとき ---
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]

        # --- 複数ファイルドロップに対応（最初の1つのみ使用） ---
        if " " in raw and not os.path.exists(raw):
            # スペース区切りで複数の場合
            first = raw.split(" ")[0]
        else:
            first = raw

        path = os.path.normpath(first)

        # --- パス確認 ---
        if not os.path.isfile(path):
            self.update_status(f"ドロップされたファイルが見つかりません: {path}", "red")
            return

        if not path.lower().endswith((".tif", ".tiff", ".png", ".jpg", ".jpeg")):
            self.update_status("対応していない拡張子です。", "red")
            return

        # --- 正常処理 ---
        self.load_new_image(path)


    # ---------------- 画像ロード関連 ---------------- #
    def select_file(self):
        path = filedialog.askopenfilename(
            title="画像ファイルを選択してください",
            filetypes=[("画像ファイル", "*.tif;*.tiff;*.png;*.jpg;*.jpeg"), ("すべてのファイル", "*.*")]
        )
        if path:
            self.load_new_image(path)
        else:
            self.update_status("ファイルが選択されませんでした。", "red")

    def load_new_image(self, path):
        self.file_path = path
        self.image = self.load_image(path)
        self.corrected_image = None
        self.base_image_for_rotation = None
        self.reset_rotation_controls()
        self.display_image(self.image)
        self.update_status(f"画像を読み込みました: {os.path.basename(path)}")


    def load_image(self, path):
        img = np.array(Image.open(path).convert("RGB"))  # ★ カラー読み込み
        # 0–255の範囲に正規化（uint8のままでOK）
        return img

    # ---------------- 自動処理 ---------------- #
    def process_image(self):
        if self.image is None:
            self.update_status("画像が読み込まれていません。", "red")
            return

        # 1) ゲル認識はグレースケールで実施
        gray = cv2.cvtColor(self.image, cv2.COLOR_RGB2GRAY)

        # 2) 多段前処理の統合でゲル矩形を高精度推定
        cropped = self.auto_crop_gel(gray)

        # 3) 傾き補正もグレースケールで
        corrected = self.auto_rotate_image(cropped)

        # 4) その結果（2D配列）をカラー変換して表示（見やすく）
        corrected_color = cv2.cvtColor(corrected, cv2.COLOR_GRAY2RGB)

        self.corrected_image = corrected_color
        self.base_image_for_rotation = corrected_color.copy()
        self.reset_rotation_controls()
        self.display_image(self.corrected_image)

        h, w = self.corrected_image.shape[:2]
        x, y, ww, hh = self.auto_rect_xywh if self.auto_rect_xywh else (0, 0, w, h)
        self.update_status(f"ゲル検出→切り取り完了（元座標 x={x}, y={y}, w={ww}, h={hh}／表示サイズ {w}x{h}）")


    # --------- 高精度ゲル検出（暗部対応：γ補正・CLAHE・背景除去の統合） --------- #
    def auto_crop_gel(self, img):
        H, W = img.shape[:2]

        def gamma_correction(im, gamma):
            table = (np.linspace(0, 1, 256) ** gamma * 255).astype(np.uint8)
            return cv2.LUT(im, table)

        def background_subtract(im, ksize=51):
            blur = cv2.GaussianBlur(im, (ksize, ksize), 0)
            sub = cv2.subtract(im, blur)
            mn, mx = float(sub.min()), float(sub.max())
            if mx > mn:
                sub = (sub - mn) / (mx - mn) * 255.0
            return sub.astype(np.uint8)

        def variants(im):
            return [
                im,
                gamma_correction(im, 0.7),
                gamma_correction(im, 0.5),
                cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(im),
                background_subtract(im, ksize=51),
            ]

        def binarize_list(im):
            out = []
            _, otsu = cv2.threshold(im, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            out.append(otsu)
            ada = cv2.adaptiveThreshold(im, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 41, 5)
            out.append(ada)
            bl = cv2.GaussianBlur(im, (7, 7), 0)
            _, otsu2 = cv2.threshold(bl, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            out.append(otsu2)
            return out

        def find_rect(bi):
            kernel = np.ones((5, 5), np.uint8)
            closed = cv2.morphologyEx(bi, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
            x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
            return (x, y, w, h)

        candidates = []
        for v in variants(img):
            for b in binarize_list(v):
                rect = find_rect(b)
                if rect is not None:
                    candidates.append(rect)

        if not candidates:
            self.update_status("ゲル領域が検出できなかったため、原画像全体を返します。", color="red")
            self.auto_rect_xywh = (0, 0, W, H)
            return img

        def score(rect):
            x, y, w, h = rect
            area = w * h
            area_frac = area / (W * H + 1e-6)
            area_score = 1.0 - abs(area_frac - 0.5) / 0.5
            area_score = max(0.0, area_score)
            aspect = (w + 1e-6) / (h + 1e-6)
            aspect_score = 1.0 - min(abs(aspect - 0.6), 1.0)
            cx, cy = x + w / 2.0, y + h / 2.0
            dx = abs(cx - W / 2.0) / (W / 2.0)
            dy = abs(cy - H / 2.0) / (H / 2.0)
            center_score = 1.0 - min((dx + dy) / 2.0, 1.0)
            return 0.5 * area_score + 0.3 * aspect_score + 0.2 * center_score

        best = max(candidates, key=score)
        x, y, w, h = best
        x = max(0, x)
        y = max(0, y)
        w = min(W - x, w)
        h = min(H - y, h)
        cropped = img[y:y + h, x:x + w]
        self.auto_rect_xywh = (x, y, w, h)
        return cropped

    # ---------------- 傾き補正（現行アルゴリズム） ---------------- #
    def auto_rotate_image(self, img):
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 120)
        angles = []
        if lines is not None:
            for rho, theta in lines[:, 0]:
                ang = np.degrees(theta) - 90.0
                if -45 <= ang <= 45:
                    angles.append(ang)
        median_angle = float(np.median(angles)) if angles else 0.0
        if abs(median_angle) < 0.1:
            return img
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def show_placeholder_text(self):
        """画像が読み込まれていないときに表示する案内メッセージ"""
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        text = "ここに画像ファイル📂をドラッグ＆ドロップしてください\nまたは「画像を選択」ボタンから開いてください"
        self.canvas.create_rectangle(0, 0, cw, ch, fill="#333333", outline="")
        self.canvas.create_text(
            cw // 2, ch // 2,
            text=text,
            fill="#aaaaaa",
            font=("Yu Gothic UI", 16, "bold"),
            justify="center"
        )


    # ---------------- 表示 ---------------- #
    def display_image(self, img):
        self.canvas.delete("all")

        if img is None:
            self.show_placeholder_text()
            return

        self.displayed_image = img
        h, w = img.shape[:2]
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        # 常にキャンバスにピッタリ収める倍率（ゲルサイズに応じて毎回自動計算）
        scale = min(max(1e-6, cw / w), max(1e-6, ch / h))
        self.scale_x = self.scale_y = float(scale)
        sw, sh = int(w * scale), int(h * scale)
        ox, oy = max(0, (cw - sw) // 2), max(0, (ch - sh) // 2)
        img_resized = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(img_resized))
        self.canvas.create_image(ox, oy, anchor="nw", image=self.tk_image)

    # ---------------- 手動回転（プレビュー＆確定） ---------------- #
    def on_rotate_preview(self, _ev=None):
        # プレビューは常に基準画像から回転 → 画質劣化なし
        base = self.base_image_for_rotation if self.base_image_for_rotation is not None else self.corrected_image
        if base is None:
            # まだ自動処理前なら原画像をベースに
            base = self.image
        if base is None:
            return
        angle = float(self.manual_angle_var.get())
        self.angle_entry.delete(0, tk.END)
        self.angle_entry.insert(0, f"{angle:.3f}")
        (h, w) = base.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(base, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        self.display_image(rotated)

    def apply_angle_from_entry(self):
        try:
            val = float(self.angle_entry.get())
        except Exception:
            self.update_status("角度は数値で入力してください。", "red")
            return
        val = max(-180.0, min(180.0, val))
        self.manual_angle_var.set(val)
        self.on_rotate_preview()

    def confirm_rotation(self):
        # 現在のプレビュー角度を確定し、corrected_imageと基準を更新
        base = self.base_image_for_rotation if self.base_image_for_rotation is not None else self.corrected_image
        if base is None:
            base = self.image
        if base is None:
            return
        angle = float(self.manual_angle_var.get())
        (h, w) = base.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        out = cv2.warpAffine(base, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        self.corrected_image = out
        self.base_image_for_rotation = out.copy()
        self.display_image(self.corrected_image)
        self.update_status(f"回転を確定しました（{angle:.3f}°）")

    def reset_rotation_controls(self):
        self.manual_angle_var.set(0.0)
        if hasattr(self, 'angle_entry') and self.angle_entry is not None:
            self.angle_entry.delete(0, tk.END)
            self.angle_entry.insert(0, "0.000")

    # ---------------- 手動トリミング ---------------- #
    def start_crop(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = None

    def draw_crop_rect(self, event):
        if self.start_x is not None and self.start_y is not None:
            if self.rect_id:
                self.canvas.delete(self.rect_id)
            self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="red")

    def finish_crop(self, event):
        if self.start_x is None or self.start_y is None:
            return
        # 左上・右下に正規化
        x0, x1 = sorted([self.start_x, event.x])
        y0, y1 = sorted([self.start_y, event.y])
        self.start_x, self.start_y = None, None

        if self.displayed_image is None:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        ih, iw = self.displayed_image.shape[0], self.displayed_image.shape[1]
        offset_x = (cw - iw * self.scale_x) / 2
        offset_y = (ch - ih * self.scale_y) / 2

        # キャンバス -> 画像座標変換
        x0_img = int((x0 - offset_x) / self.scale_x)
        y0_img = int((y0 - offset_y) / self.scale_y)
        x1_img = int((x1 - offset_x) / self.scale_x)
        y1_img = int((y1 - offset_y) / self.scale_y)

        # 画像範囲クリップ
        x0_img, y0_img = max(0, x0_img), max(0, y0_img)
        x1_img, y1_img = min(iw, x1_img), min(ih, y1_img)

        cropped = self.displayed_image[y0_img:y1_img, x0_img:x1_img]
        if cropped.size == 0:
            self.update_status("無効な範囲です。", "red")
            return
        self.corrected_image = cropped
        self.base_image_for_rotation = self.corrected_image.copy()
        self.reset_rotation_controls()
        self.display_image(cropped)
        self.update_status("選択範囲をトリミングしました。")

    # ---------------- 保存（DPI設定あり・元ファイル名を初期入力） ---------------- #
    def change_dpi(self):
        win = tk.Toplevel(self.root)
        win.title("DPI設定")
        tk.Label(win, text="保存DPIを選択してください:").pack(pady=6)
        dpi_var = tk.IntVar(value=self.save_dpi)
        for val in [72, 150, 300, 600]:
            tk.Radiobutton(win, text=f"{val} dpi", variable=dpi_var, value=val).pack(anchor='w')

        def apply_dpi():
            self.save_dpi = dpi_var.get()
            self.update_status(f"保存DPIを {self.save_dpi} に設定しました。")
            win.destroy()

        tk.Button(win, text="OK", command=apply_dpi).pack(pady=8)

    def export_corrected_image(self):
        if self.corrected_image is None:
            self.update_status("補正された画像がありません。", "red")
            return
        initial_name = os.path.basename(self.file_path) if self.file_path else None
        path = filedialog.asksaveasfilename(
            initialfile=initial_name,
            defaultextension=".tif",
            filetypes=[("TIFF", "*.tif;*.tiff"), ("PNG", "*.png"), ("JPEG", "*.jpg;*.jpeg")]
        )
        if not path:
            return
        try:
            Image.fromarray(self.corrected_image).save(path, dpi=(self.save_dpi, self.save_dpi))
            self.update_status(f"保存しました: {path} ({self.save_dpi} dpi)")
        except Exception as e:
            self.update_status(f"保存エラー: {e}", "red")

    # ---------------- リサイズ ---------------- #
    def on_resize(self, event):
        if self.displayed_image is not None:
            self.display_image(self.displayed_image)
        else:
            self.show_placeholder_text()



if __name__ == "__main__":
    root = make_root()
    app = GelImageProcessor(root)
    root.minsize(800, 600)
    root.mainloop()
