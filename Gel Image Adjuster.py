import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
import cv2
from PIL import Image, ImageTk

class GelImageProcessor:
    def __init__(self, root):
        self.root = root
        self.file_path = None
        self.image = None
        self.cropped_image = None
        self.corrected_image = None
        self.displayed_image = None  # 表示する画像を保持するための変数
        self.history = []  # 履歴スタック（画像の履歴）
        self.history_index = -1  # 現在の履歴のインデックス

        # スケール情報
        self.scale_x = 1
        self.scale_y = 1

        # トリミング用
        self.start_x = None
        self.start_y = None
        self.rect_id = None

        # UI構築
        self.create_ui()

    def create_ui(self):
        self.root.title("ゲル画像処理ツール")

        # ツールバー
        toolbar = tk.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # 前に戻る（Undo）ボタン
        undo_icon = self.create_arrow_icon("left")  # 左矢印
        undo_button = tk.Button(toolbar, text="Undo", image=undo_icon, compound="left", command=self.undo)
        undo_button.grid(row=0, column=0, padx=5)
        undo_button.image = undo_icon  # ボタンに画像をセット

        # 進む（Redo）ボタン
        redo_icon = self.create_arrow_icon("right")  # 右矢印
        redo_button = tk.Button(toolbar, text="Redo", image=redo_icon, compound="left", command=self.redo)
        redo_button.grid(row=0, column=1, padx=5)
        redo_button.image = redo_icon  # ボタンに画像をセット

        # ファイル選択ボタン
        select_button = tk.Button(self.root, text="画像ファイルを選択", command=self.select_file)
        select_button.pack(pady=10)

        # 画像処理実行ボタン
        process_button = tk.Button(self.root, text="画像処理を実行", command=self.process_image)
        process_button.pack(pady=10)

        # 保存ボタン
        save_button = tk.Button(self.root, text="補正画像を保存", command=self.export_corrected_image)
        save_button.pack(pady=10)

        # ステータス表示
        self.status_label = tk.Label(self.root, text="ステータス: 待機中", fg="blue")
        self.status_label.pack(pady=10)

        # キャンバス
        self.canvas = tk.Canvas(self.root, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_resize)  # ウィンドウのリサイズイベントをバインド
        self.canvas.bind("<Button-1>", self.start_crop)
        self.canvas.bind("<B1-Motion>", self.draw_crop_rect)
        self.canvas.bind("<ButtonRelease-1>", self.finish_crop)

    def create_arrow_icon(self, direction):
        """指定された方向（'left' または 'right'）の矢印アイコンを作成"""
        icon = tk.PhotoImage(width=20, height=20)
        if direction == "left":
            icon.put("#000000", to=(0, 0, 10, 20))  # 左矢印
            icon.put("#000000", to=(10, 0, 20, 20))
        elif direction == "right":
            icon.put("#000000", to=(10, 0, 20, 20))  # 右矢印
            icon.put("#000000", to=(0, 0, 10, 20))
        return icon

    def update_status(self, message, color="blue"):
        self.status_label.config(text=f"ステータス: {message}", fg=color)

    def select_file(self):
        self.file_path = filedialog.askopenfilename(
            title="画像ファイルを選択してください",
            filetypes=[("画像ファイル", "*.tif;*.png;*.jpg;*.jpeg"), ("すべてのファイル", "*.*")],
        )
        if not self.file_path:
            self.update_status("ファイルが選択されませんでした。", "red")
            return
        self.image = self.load_image(self.file_path)
        self.display_image(self.image)
        self.update_status("画像を読み込みました。")

    def load_image(self, path):
        img = np.array(Image.open(path).convert("L"))
        img = (img - np.min(img)) / (np.max(img) - np.min(img)) * 255
        return img.astype(np.uint8)

    def auto_crop_gel(self, img):
        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        _, binary = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        gel_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(gel_contour)

        # 範囲をさらに広げる
        offset = 150  # より広い範囲を設定
        x = max(0, x - offset)
        y = max(0, y - offset)
        w = min(img.shape[1] - x, w + 2 * offset)
        h = min(img.shape[0] - y, h + 2 * offset)

        cropped = img[y:y + h, x:x + w]
        return cropped

    def auto_rotate_image(self, img):
        # エッジ検出
        edges = cv2.Canny(img, 50, 150, apertureSize=3)

        # Hough変換で線を検出
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        if lines is not None:
            angles = []
            for rho, theta in lines[:, 0]:
                angle = np.degrees(theta) - 90  # ラジアンから角度に変換
                if -45 < angle < 45:  # 有効な傾き角度の範囲に限定
                    angles.append(angle)
            if len(angles) > 0:
                median_angle = np.median(angles)  # 中央値を使用して傾き補正
                print(f"Detected median angle for rotation: {median_angle}")
                (h, w) = img.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                return rotated
            else:
                print("No valid angles detected.")
        else:
            print("No lines detected for rotation.")
        return img

    def process_image(self):
        """画像処理（自動トリミングと傾き補正）を実行"""
        if self.image is None:
            self.update_status("画像が読み込まれていません。", "red")
            return

        # 自動トリミング
        cropped = self.auto_crop_gel(self.image)

        # 自動傾き補正
        corrected = self.auto_rotate_image(cropped)

        self.corrected_image = corrected
        self.save_to_history(self.corrected_image)
        self.display_image(self.corrected_image)
        self.update_status("画像処理を実行しました。")

    def save_to_history(self, image):
        """履歴に画像を保存する"""
        # 履歴スタックのインデックスが最後でない場合、以降の履歴を切り捨てる
        if self.history_index != len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
        self.history.append(image)
        self.history_index += 1

    def display_image(self, img):
        self.canvas.delete("all")
        self.displayed_image = img  # 表示する画像を保存
        height, width = img.shape
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # 画像がキャンバスのサイズに収まるようにスケール
        scale = min(canvas_width / width, canvas_height / height)
        self.scale_x = scale
        self.scale_y = scale
        scaled_width = int(width * scale)
        scaled_height = int(height * scale)

        # キャンバスのサイズを画像サイズに合わせて変更
        # キャンバスのサイズは変更しないようにする
        img_resized = cv2.resize(img, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)
        img = Image.fromarray(img_resized)
        self.tk_image = ImageTk.PhotoImage(image=img)

        # 画像をキャンバスの中央に配置
        self.canvas.create_image((canvas_width - scaled_width) // 2, (canvas_height - scaled_height) // 2, anchor="nw", image=self.tk_image)

    def start_crop(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = None

    def draw_crop_rect(self, event):
        if self.start_x and self.start_y:
            if self.rect_id:
                self.canvas.delete(self.rect_id)
            self.rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, event.x, event.y, outline="red"
            )

    def finish_crop(self, event):
        if self.start_x and self.start_y:
            x0, y0, x1, y1 = self.start_x, self.start_y, event.x, event.y
            self.start_x, self.start_y = None, None

            x0, x1 = sorted([x0, x1])
            y0, y1 = sorted([y0, y1])

            # トリミング領域を取得して処理
            cropped = self.displayed_image[int(y0 / self.scale_y):int(y1 / self.scale_y),
                                  int(x0 / self.scale_x):int(x1 / self.scale_x)]
            self.display_image(cropped)

    def export_corrected_image(self):
        if self.corrected_image is None:
            self.update_status("補正された画像がありません。", "red")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
        )
        if not save_path:
            self.update_status("保存がキャンセルされました。", "red")
            return

        # トリミング後の画像を保存
        cv2.imwrite(save_path, self.displayed_image)
        self.update_status(f"補正された画像を保存しました: {save_path}")

    def undo(self, event=None):
        """前に戻る（Undo）"""
        if self.history_index > 0:
            self.history_index -= 1
            self.corrected_image = self.history[self.history_index]
            self.display_image(self.corrected_image)
            self.update_status(f"前の画像に戻りました。ステータス: {self.history_index + 1} / {len(self.history)}")
        else:
            self.update_status("これ以上戻れません。", "red")

    def redo(self, event=None):
        """進む（Redo）"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.corrected_image = self.history[self.history_index]
            self.display_image(self.corrected_image)
            self.update_status(f"進みました。ステータス: {self.history_index + 1} / {len(self.history)}")
        else:
            self.update_status("これ以上進めません。", "red")

    def on_resize(self, event):
        """ウィンドウのサイズ変更時にキャンバスをリサイズ"""
        if self.displayed_image is not None:
            self.display_image(self.displayed_image)  # ウィンドウサイズに合わせて画像を再表示

if __name__ == "__main__":
    root = tk.Tk()
    app = GelImageProcessor(root)
    root.mainloop()
