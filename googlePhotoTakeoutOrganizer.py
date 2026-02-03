import os
import shutil
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
from PIL import Image
from PIL.ExifTags import TAGS

class Logger:
    def __init__(self, filename, text_widget):
        self.filename = filename
        self.text_widget = text_widget
        # 【修正箇所1】ログファイル作成時にエラーを無視する設定を追加
        self.file = open(self.filename, 'a', encoding='utf-8', errors='ignore')

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {level} - {message}\n"
        
        # GUIへの出力
        self.text_widget.after(0, self._update_gui, log_entry)
        
        # ファイルへの出力
        self.file.write(log_entry)
        self.file.flush()

    def _update_gui(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)

    def close(self):
        self.file.close()

class GooglePhotoOrganizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Photo Takeout Organizer v1.0.1")
        self.root.geometry("700x550")

        self.setup_ui()
        
        self.source_dir = ""
        self.dest_dir = ""
        self.logger = None
        self.processing = False

    def setup_ui(self):
        # メインフレーム
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 説明ラベル
        tk.Label(main_frame, text="Google Takeout で書き出した写真データを年月別に整理します。", font=("MS Gothic", 10, "bold")).pack(pady=(0, 10))

        # 元フォルダ選択
        src_frame = tk.Frame(main_frame)
        src_frame.pack(fill=tk.X, pady=5)
        tk.Label(src_frame, text="元のデータフォルダ:").pack(side=tk.LEFT)
        self.src_label = tk.Label(src_frame, text="選択されていません", fg="blue", wraplength=400)
        self.src_label.pack(side=tk.LEFT, padx=10)
        tk.Button(src_frame, text="選択", command=self.select_source).pack(side=tk.RIGHT)

        # 出力先フォルダ選択
        dst_frame = tk.Frame(main_frame)
        dst_frame.pack(fill=tk.X, pady=5)
        tk.Label(dst_frame, text="整理先の出力フォルダ:").pack(side=tk.LEFT)
        self.dst_label = tk.Label(dst_frame, text="選択されていません", fg="blue", wraplength=400)
        self.dst_label.pack(side=tk.LEFT, padx=10)
        tk.Button(dst_frame, text="選択", command=self.select_dest).pack(side=tk.RIGHT)

        # 実行ボタン
        self.run_btn = tk.Button(main_frame, text="整理を開始する", command=self.start_process, 
                                 bg="#4CAF50", fg="white", font=("MS Gothic", 12, "bold"), height=2)
        self.run_btn.pack(fill=tk.X, pady=20)

        # ログ表示エリア
        tk.Label(main_frame, text="処理ログ:").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(main_frame, height=15, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def select_source(self):
        path = filedialog.askdirectory(title="Google Takeout のフォルダを選択")
        if path:
            self.source_dir = path
            self.src_label.config(text=path)

    def select_dest(self):
        path = filedialog.askdirectory(title="出力先の空フォルダを選択")
        if path:
            self.dest_dir = path
            self.dst_label.config(text=path)

    def get_date_from_exif(self, file_path):
        """画像からEXIF情報を取得"""
        try:
            img = Image.open(file_path)
            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    tag_name = TAGS.get(tag, tag)
                    if tag_name == 'DateTimeOriginal':
                        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
        except:
            pass
        return None

    def get_date_from_json(self, file_path):
        """Google PhotosのJSONメタデータから日時を取得"""
        json_file_path = file_path + ".json"
        if os.path.exists(json_file_path):
            try:
                # 【修正箇所2】JSON読み込み時にエラーを無視する設定を追加
                with open(json_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)
                    # photoTakenTime または creationTime を取得
                    timestamp = int(data.get('photoTakenTime', {}).get('timestamp', 0))
                    if timestamp == 0:
                        timestamp = int(data.get('creationTime', {}).get('timestamp', 0))
                    
                    if timestamp > 0:
                        return datetime.fromtimestamp(timestamp)
            except Exception as e:
                if self.logger:
                    self.logger.log(f"[警告] JSON解析失敗 {os.path.basename(file_path)}: {e}", "WARNING")
        return None

    def process_files(self):
        self.processing = True
        self.run_btn.config(state=tk.DISABLED)
        
        log_file = os.path.join(self.dest_dir, f"google_takeout_organizer.log")
        self.logger = Logger(log_file, self.log_area)
        self.logger.log("処理を開始します...")

        # Googleフォトの開始日 (2015年5月28日)
        google_photos_start = datetime(2015, 5, 28)
        now = datetime.now()

        total_files = 0
        moved_files = 0

        for root_dir, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith('.json'):
                    continue
                
                total_files += 1
                file_path = os.path.join(root_dir, file)
                
                # 日時特定の優先順位: 1.JSON 2.EXIF 3.ファイル更新日時
                target_date = self.get_date_from_json(file_path)
                if not target_date:
                    target_date = self.get_date_from_exif(file_path)
                if not target_date:
                    target_date = datetime.fromtimestamp(os.path.getmtime(file_path))

                # 不適切な日時の場合はdateunknownへ
                if target_date < google_photos_start or target_date > now:
                    dest_subdir = "dateunknown"
                else:
                    dest_subdir = target_date.strftime('%Y/%m')

                target_dest_dir = os.path.join(self.dest_dir, dest_subdir)
                os.makedirs(target_dest_dir, exist_ok=True)

                # 同名ファイル対策
                dest_file_path = os.path.join(target_dest_dir, file)
                if os.path.exists(dest_file_path):
                    name, ext = os.path.splitext(file)
                    dest_file_path = os.path.join(target_dest_dir, f"{name}_{total_files}{ext}")

                try:
                    shutil.copy2(file_path, dest_file_path)
                    moved_files += 1
                except Exception as e:
                    self.logger.log(f"[エラー] コピー失敗 {file}: {e}", "ERROR")

        self.logger.log(f"処理完了: 全 {total_files} ファイル中 {moved_files} ファイルを整理しました。")
        self.logger.close()
        self.processing = False
        self.run_btn.config(state=tk.NORMAL)
        messagebox.showinfo("完了", "写真の整理が完了しました！\n出力フォルダのログをご確認ください。")

    def start_process(self):
        if not self.source_dir or not self.dest_dir:
            messagebox.showwarning("警告", "元フォルダと出力フォルダの両方を選択してください。")
            return
        
        if self.processing:
            return

        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = GooglePhotoOrganizer(root)
    root.mainloop()