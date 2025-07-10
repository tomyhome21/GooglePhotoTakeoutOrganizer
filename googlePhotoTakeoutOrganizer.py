import os
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import shutil
import json
import re
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import sys

# Tkinterのルートウィンドウを作成（ユーザーには見えない）
root = tk.Tk()
root.withdraw()    # メインウィンドウを非表示にする

# --- プログレスウィンドウ関連の変数と関数 (変更なし) ---
progress_window = None
progress_label = None
progress_bar = None
total_files_to_process = 0
current_file_count = 0

def create_progress_window():
    global progress_window, progress_label, progress_bar
    progress_window = tk.Toplevel(root)
    progress_window.title("処理中...")
    progress_window.geometry("400x120")
    progress_window.resizable(False, False)
    progress_window.attributes("-topmost", True)
    tk.Label(progress_window, text="メディアファイルを整理中...", font=("Arial", 12)).pack(pady=10)
    progress_label = tk.Label(progress_window, text="準備中...", font=("Arial", 10))
    progress_label.pack(pady=5)
    progress_bar = ttk.Progressbar(progress_window, orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=5)
    progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
    root.update_idletasks()
    root.update()

def update_progress(current_file_path, processed_count, total_count):
    if progress_window and progress_label and progress_bar:
        display_filename = os.path.basename(current_file_path)
        progress_label.config(text=f"処理中: {display_filename}\n({processed_count}/{total_count} ファイル)")
        if total_count > 0:
            progress_bar["value"] = (processed_count / total_count) * 100
        else:
            progress_bar["value"] = 0
        root.update_idletasks()
        root.update()

def destroy_progress_window():
    global progress_window
    if progress_window:
        progress_window.destroy()
        progress_window = None

# --- ロギング関連のクラスと関数 (修正箇所あり) ---

# グローバルロガーインスタンス
app_logger = None

class CustomLogger:
    """ログファイルとコンソールに書き込むためのカスタムロガー"""
    def __init__(self, filename=None):
        self.filename = filename
        self.file = None

    def _log_to_console(self, message):
        """コンソール（または可能な限り標準出力）にメッセージを出力する"""
        try:
            # sys.__stdout__ が存在し、かつ write メソッドを持つか確認
            if sys.__stdout__ and hasattr(sys.__stdout__, 'write'):
                sys.__stdout__.write(message + '\n')
                sys.__stdout__.flush()
            else:
                # __stdout__ が使えない場合（例: --noconsole ビルド時）は、
                # Tkinter のメッセージボックスで重要なエラーを通知
                # ただし、ロギングの全てのメッセージをメッセージボックスに出すと煩雑になるため、
                # ここでは最低限のシステムレベルのエラーを想定。
                # 通常の処理中のログはファイルのみに依存させる。
                pass # ここでは、コンソールがない場合は何もしない（ログファイルへは出力される）
                     # あるいは、必要に応じて messagebox.showinfo などで代替するが、
                     # 実行中に大量に出力されるとGUIがフリーズするため非推奨。
        except Exception as e:
            # これ自体が失敗した場合、どうしようもないが、念のため捕捉
            messagebox.showerror("ロギングエラー", f"コンソール出力に失敗しました: {e}\nメッセージ: {message}")

    def open(self):
        if self.filename:
            try:
                self.file = open(self.filename, 'a', encoding='utf-8')
                self._log_to_console(f"[システム] ログファイルを開きました: {self.filename}")
            except IOError as e:
                messagebox.showerror("ログファイルエラー", f"ログファイル '{self.filename}' を開けませんでした: {e}\nログはコンソールにのみ出力されます。")
                self._log_to_console(f"[システムエラー] ログファイル '{self.filename}' を開けませんでした: {e}")
                self.file = None
        else:
            self._log_to_console("[システム] ログファイルは指定されていません。コンソールにのみ出力します。")

    def write(self, message):
        # ファイルに書き込み (ファイルが開かれている場合のみ)
        if self.file:
            try:
                self.file.write(message + '\n') # 改行を自動追加
                self.file.flush()
            except Exception as e:
                self._log_to_console(f"[ログエラー] ファイルへの書き込みに失敗しました: {e}. メッセージ: {message}")
                self.close() # エラー発生時はファイルを閉じる
        
        # コンソールにも書き込み（これは、ファイルへの書き込みが成功した場合も失敗した場合も行われる）
        # ただし、_log_to_console はコンソールがない場合は何もしない
        self._log_to_console(message)

    def flush(self):
        if self.file:
            self.file.flush()

    def close(self):
        if self.file:
            try:
                self.file.close()
                self._log_to_console(f"[システム] ログファイルを閉じました: {self.filename}")
            except Exception as e:
                self._log_to_console(f"[ログエラー] ログファイルのクローズに失敗しました: {e}")
            self.file = None

def setup_logger(log_file_path=None):
    """ロガーをセットアップする。"""
    global app_logger
    if app_logger: # 既にロガーがある場合は閉じてから再設定
        app_logger.close()
    
    app_logger = CustomLogger(log_file_path)
    app_logger.open()
    app_logger.write("\n--- ロガー初期化完了 ---")

def cleanup_logger():
    """ロガーをクリーンアップする。"""
    global app_logger
    if app_logger:
        app_logger.write("--- ロギング終了 ---")
        app_logger.close()
        app_logger = None

# --- ここから下の関数は、app_logger.write() に置き換え済みのため変更なし ---

def select_folder(title, initial_dir=None):
    folder_path = filedialog.askdirectory(
        title=title,
        initialdir=initial_dir if initial_dir else os.path.expanduser('~'),
    )
    return folder_path

def set_file_times(file_path, new_timestamp):
    try:
        os.utime(file_path, (new_timestamp, new_timestamp))
        return True
    except Exception as e:
        app_logger.write(f'    [エラー] 日時設定失敗 \'{os.path.basename(file_path)}\': {e}')
        return False

def copy_file_to_date_folder(file_path, target_date, output_root_path):
    try:
        year_folder_path = os.path.join(output_root_path, str(target_date.year))
        month_folder_name = f'{target_date.month:02d}'
        month_folder_path = os.path.join(year_folder_path, month_folder_name)

        os.makedirs(month_folder_path, exist_ok=True)
        destination_path = os.path.join(month_folder_path, os.path.basename(file_path))

        if os.path.exists(destination_path):
            if os.path.getsize(file_path) == os.path.getsize(destination_path):
                app_logger.write(f'    [スキップ] \'{os.path.basename(file_path)}\' は既に移動先に存在し、内容も同じと判断しました。')
                return False
            else:
                app_logger.write(f'    [警告] \'{os.path.basename(file_path)}\' は移動先に存在しますが、サイズが異なります。コピーをスキップします。')
                return False
            
        shutil.copy2(file_path, destination_path)
        if set_file_times(destination_path, target_date.timestamp()):
            app_logger.write(f'    コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (日時設定済み)')
            return True
        else:
            app_logger.write(f'    コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (日時設定失敗)')
            return True
    except Exception as e:
        app_logger.write(
            f'    [エラー] コピー失敗 \'{os.path.basename(file_path)}\' -> \'{month_folder_path}\': {e}'
        )
        return False

def copy_file_to_dateunknown_folder(file_path, output_root_path):
    try:
        dateunknown_folder_path = os.path.join(output_root_path, 'dateunknown')
        os.makedirs(dateunknown_folder_path, exist_ok=True)
        destination_path = os.path.join(dateunknown_folder_path, os.path.basename(file_path))

        if os.path.exists(destination_path):
            if os.path.getsize(file_path) == os.path.getsize(destination_path):
                app_logger.write(f'    [スキップ] \'{os.path.basename(file_path)}\' は既にdateunknownに存在し、内容も同じと判断しました。')
                return False
            else:
                app_logger.write(f'    [警告] \'{os.path.basename(file_path)}\' はdateunknownに存在しますが、サイズが異なります。コピーをスキップします。')
                return False

        shutil.copy2(file_path, destination_path)
        app_logger.write(f'    コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (dateunknown)')
        return True
    except Exception as e:
        app_logger.write(
            f'    [エラー] dateunknownへのコピー失敗 \'{os.path.basename(file_path)}\': {e}'
        )
        return False

def get_json_metadata_path(media_path, takeout_root_path):
    media_filename = os.path.basename(media_path)
    media_filename_without_ext = os.path.splitext(media_filename)[0]
    json_name_patterns = [
        media_filename + '.json',
        media_filename_without_ext + '.json',
        media_filename + '.supplemental-metadata.json',
        media_filename_without_ext + '.supplemental-metadata.json'
    ]
    for pattern in json_name_patterns:
        json_path_same_dir = os.path.join(os.path.dirname(media_path), pattern)
        if os.path.exists(json_path_same_dir):
            return json_path_same_dir
    for root_dir, _, files in os.walk(takeout_root_path):
        for file_in_dir in files:
            if file_in_dir in json_name_patterns:
                json_candidate_path = os.path.join(root_dir, file_in_dir)
                if os.path.exists(json_candidate_path):
                    return json_candidate_path
    return None

def parse_japanese_date(date_string):
    tz_map = {
        'JST': datetime.timezone(datetime.timedelta(hours=9)),
        'UTC': datetime.timezone.utc,
        'GMT': datetime.timezone.utc,
        'PST': datetime.timezone(datetime.timedelta(hours=-8)),
        'PDT': datetime.timezone(datetime.timedelta(hours=-7)),
    }
    date_string = date_string.replace('年', '-').replace('月', '-').replace('日', '')
    date_string = date_string.replace('午前', 'AM').replace('午後', 'PM')
    match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})\s*(?:(\d{1,2}:\d{2}:\d{2})\s*(AM|PM)?)?\s*([A-Z]{2,5})?', date_string, re.IGNORECASE)
    if match:
        date_part = match.group(1)
        time_part = match.group(2)
        ampm_part = match.group(3)
        tz_part = match.group(4)
        time_str = ""
        if time_part:
            time_str = f"{time_part}{' ' + ampm_part if ampm_part else ''}"
            
        if time_str:
            if ampm_part:
                dt_format = '%Y-%m-%d %I:%M:%S %p'
            else:
                dt_format = '%Y-%m-%d %H:%M:%S'
            full_dt_str = f"{date_part} {time_str}"
        else:
            dt_format = '%Y-%m-%d'
            full_dt_str = date_part
        try:
            dt_obj = datetime.datetime.strptime(full_dt_str, dt_format)
            if tz_part and tz_part.upper() in tz_map:
                dt_obj = dt_obj.replace(tzinfo=tz_map[tz_part.upper()])
            elif tz_part:
                app_logger.write(f"    [警告] 未知のタイムゾーン '{tz_part}' が検出されました。UTCとして処理します。")
                dt_obj = dt_obj.replace(tzinfo=datetime.timezone.utc)
            else:
                dt_obj = dt_obj.astimezone()
            return dt_obj
        except ValueError:
            pass
    return None

def get_date_from_json(json_file_path):
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            if 'photoTakenTime' in json_data and 'timestamp' in json_data['photoTakenTime']:
                try:
                    timestamp_unix = int(json_data['photoTakenTime']['timestamp'])
                    return datetime.datetime.fromtimestamp(timestamp_unix, tz=datetime.timezone.utc).astimezone()
                except (ValueError, TypeError):
                    pass
            elif 'creationTime' in json_data and 'timestamp' in json_data['creationTime']:
                try:
                    timestamp_unix = int(json_data['creationTime']['timestamp'])
                    return datetime.datetime.fromtimestamp(timestamp_unix, tz=datetime.timezone.utc).astimezone()
                except (ValueError, TypeError):
                    pass
            if 'photoTakenTime' in json_data and 'formatted' in json_data['photoTakenTime']:
                formatted_date_str = json_data['photoTakenTime']['formatted']
                parsed_dt = parse_japanese_date(formatted_date_str)
                if parsed_dt:
                    return parsed_dt
            elif 'creationTime' in json_data and 'formatted' in json_data['creationTime']:
                formatted_date_str = json_data['creationTime']['formatted']
                parsed_dt = parse_japanese_date(formatted_date_str)
                if parsed_dt:
                    return parsed_dt
            return None
    except (json.JSONDecodeError, FileNotFoundError, KeyError, TypeError) as e:
        app_logger.write(f'    [警告] JSONファイル \'{os.path.basename(json_file_path)}\' の解析に失敗しました: {e}')
        return None

def get_date_from_exif(file_path):
    try:
        if not file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.heic')):
            return None
        with Image.open(file_path) as img:
            try:
                exif_data = img._getexif() 
            except AttributeError:
                return None
            except Exception as e:
                app_logger.write(f'    [警告] EXIFデータの取得中にエラーが発生しました \'{os.path.basename(file_path)}\': {e}')
                return None
            if exif_data is None:
                return None
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if tag_name in ('DateTimeOriginal', 'DateTimeDigitized'):
                    try:
                        dt_obj = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                        return dt_obj.astimezone()  
                    except ValueError:
                        pass
            if 'DateTime' in TAGS:
                tag_id = next((k for k, v in TAGS.items() if v == 'DateTime'), None)
                if tag_id and tag_id in exif_data:
                    try:
                        dt_obj = datetime.datetime.strptime(exif_data[tag_id], '%Y:%m:%d %H:%M:%S')
                        return dt_obj.astimezone()
                    except ValueError:
                        pass
    except Exception as e:
        app_logger.write(f'    [警告] EXIF情報からの日時取得に失敗しました \'{os.path.basename(file_path)}\': {e}')
    return None

def is_after_google_photos_release(target_datetime):
    google_photos_release_date = datetime.datetime(2015, 5, 28, 0, 0, 0)
    if target_datetime.tzinfo is None or target_datetime.tzinfo.utcoffset(target_datetime) is None:
        target_datetime = target_datetime.astimezone()
    google_photos_release_date_aware = google_photos_release_date.astimezone(target_datetime.tzinfo)
    now_aware = datetime.datetime.now(target_datetime.tzinfo)
    return google_photos_release_date_aware <= target_datetime <= now_aware

def process_media_files(takeout_root_path, output_root_path, target_folders_to_process, update_progress_callback):
    total_processed_files = 0
    total_copied_to_dated_folders = 0
    total_copied_to_dateunknown = 0
    total_skipped_existing_files = 0
    total_failed_files = 0
    media_extensions = ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.jpg', '.jpeg', '.png', '.heic', '.webp', '.gif')
    all_media_files = []
    for folder_path_to_process in target_folders_to_process:
        for root_dir, _, files in os.walk(folder_path_to_process):
            for file in files:
                if file.lower().endswith(media_extensions):
                    all_media_files.append(os.path.join(root_dir, file))
    total_files_for_progress = len(all_media_files)
    current_file_index = 0

    app_logger.write(f'--- 処理対象となるメディアファイルの総数: {total_files_for_progress} 件 ---')

    for file_full_path in all_media_files:
        current_file_index += 1
        total_processed_files += 1
        update_progress_callback(file_full_path, current_file_index, total_files_for_progress)
        target_datetime = None
        copy_to_dateunknown_flag = False

        app_logger.write(f"\n[処理中] ファイル: {os.path.basename(file_full_path)}")

        json_metadata_path = get_json_metadata_path(file_full_path, takeout_root_path)
        if json_metadata_path:
            app_logger.write(f"    JSONファイルが見つかりました: {os.path.basename(json_metadata_path)}")
            target_datetime = get_date_from_json(json_metadata_path)
            if target_datetime:
                app_logger.write(f'    JSONから日時取得: {target_datetime.strftime('%Y/%m/%d %H:%M:%S %Z%z')}')
                if not is_after_google_photos_release(target_datetime):
                    app_logger.write(f'    [情報] JSONの日時 ({target_datetime.strftime('%Y/%m/%d %H:%M:%S')}) がGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象。')
                    copy_to_dateunknown_flag = True
            else:
                app_logger.write(f'    [警告] JSONから有効な日時情報を取得できませんでした: \'{os.path.basename(json_metadata_path)}\'. 次の取得方法を試行。')
        else:
            app_logger.write(f'    [情報] 対応するJSONファイルが見つかりませんでした. 次の取得方法を試行。')

        if target_datetime is None:
            target_datetime = get_date_from_exif(file_full_path)
            if target_datetime:
                app_logger.write(f'    EXIFから日時取得: {target_datetime.strftime('%Y/%m/%d %H:%M:%S %Z%z')}')
                if not is_after_google_photos_release(target_datetime):
                    app_logger.write(f'    [情報] EXIFの日時 ({target_datetime.strftime('%Y/%m/%d %H:%M:%S')}) がGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象。')
                    copy_to_dateunknown_flag = True
                else:
                    copy_to_dateunknown_flag = False
            else:
                app_logger.write(f'    [警告] EXIFから有効な日時情報を取得できませんでした. 次の取得方法を試行。')

        if target_datetime is None:
            try:
                current_file_mod_time_timestamp = os.path.getmtime(file_full_path)
                target_datetime = datetime.datetime.fromtimestamp(current_file_mod_time_timestamp).astimezone()  
                app_logger.write(f'    ファイルシステムの更新日時を使用: {target_datetime.strftime('%Y/%m/%d %H:%M:%S %Z%z')}')
                if not is_after_google_photos_release(target_datetime):
                    app_logger.write(f'    [情報] ファイルシステムの日時 ({target_datetime.strftime('%Y/%m/%d %H:%M:%S')}) もGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象。')
                    copy_to_dateunknown_flag = True
                else:
                    copy_to_dateunknown_flag = False  
            except Exception as e:
                app_logger.write(f'    [エラー] ファイルシステムの日時取得にも失敗しました: {e}')
                total_failed_files += 1
                copy_to_dateunknown_flag = True
                target_datetime = None

        if target_datetime is None or copy_to_dateunknown_flag:
            app_logger.write(f'    [決定] 日時特定不可、またはリリース日外のため \'dateunknown\' フォルダへコピーします。')
            if copy_file_to_dateunknown_folder(file_full_path, output_root_path):
                total_copied_to_dateunknown += 1
            else:
                if os.path.exists(os.path.join(output_root_path, 'dateunknown', os.path.basename(file_full_path))):
                    total_skipped_existing_files += 1
                else:
                    total_failed_files += 1
        else:
            app_logger.write(f'    [決定] 日時が特定されたため、正しい年/月フォルダへコピーします。')
            if copy_file_to_date_folder(
                file_full_path, target_datetime, output_root_path
            ):
                total_copied_to_dated_folders += 1
            else:
                expected_dest_path = os.path.join(output_root_path, str(target_datetime.year), f'{target_datetime.month:02d}', os.path.basename(file_full_path))
                if os.path.exists(expected_dest_path):
                    total_skipped_existing_files += 1
                else:
                    total_failed_files += 1

    return (
        total_processed_files,
        total_copied_to_dated_folders,
        total_copied_to_dateunknown,
        total_skipped_existing_files,
        total_failed_files,
    )

# --- メイン処理の実行部分 ---
def main():
    # ロガーを最初に初期化 (ログファイルはまだ指定しない)
    setup_logger()

    messagebox.showinfo(
        'スクリプト開始: Google Takeout オーガナイザー (EXIF対応版)',
        '「Google Takeout オーガナイザー」へようこそ！\n\n'
        'このスクリプトは、Google Takeoutで展開されたデータのルートフォルダを選択し、'
        'その中の**全ての動画ファイルと写真ファイルを対象**に整理を行います。\n\n'
        #'**【重要：事前の準備】**\n'
        #'**EXIF情報から日時を取得するためには、Pythonの`Pillow`ライブラリが必要です。**\n'
        #'コマンドプロンプトやターミナルで、以下のコマンドを実行してインストールしてください。\n'
        #'`pip install Pillow`\n\n'
        '**【重要：スクリプトの動作】**\n'
        '本ツールは、**元のGoogle Takeoutデータは一切変更しません**。\n'
        '整理されたファイルは、後ほど指定していただく**新しい出力先フォルダ**の中に、'
        '`YYYY/MM`形式のフォルダ構造と「`dateunknown`」フォルダでコピーされます。\n\n'
        'もし撮影日時が**Googleフォトのサービス開始（2015年5月28日）より古いファイル、未来のファイル、または日時が特定できないファイル**は、'
        '全て「**dateunknown**」フォルダにコピーされます。\n\n'
        '続行するには、「OK」をクリックしてGoogle TakeoutでダウンロードしたGoogleフォトのフォルダを選択してください。'
    )
    takeout_root_path = select_folder('Google TakeoutでダウンロードしたGoogleフォトのフォルダを選択 (元のデータ)')

    if not takeout_root_path:
        messagebox.showwarning('処理中断', 'Google Takeoutのルートフォルダが選択されませんでした。スクリプトを終了します。')
        cleanup_logger() # 終了時にロガーをクリーンアップ
        return

    messagebox.showinfo(
        '出力先フォルダの選択',
        '次に、整理されたファイルがコピーされる新しい出力先フォルダを選択してください。\n'
        '既存のフォルダを選択しても構いませんし、新しいフォルダを作成しても構いません。\n'
        'このフォルダの中に、整理された年/月フォルダと「dateunknown」フォルダが作成されます。'
    )
    output_root_path = select_folder('整理ファイルの出力先フォルダを選択 (新規または既存)')

    if not output_root_path:
        messagebox.showwarning('処理中断', '出力先フォルダが選択されませんでした。スクリプトを終了します。')
        cleanup_logger() # 終了時にロガーをクリーンアップ
        return

    if not os.path.exists(output_root_path):
        try:
            os.makedirs(output_root_path)
            app_logger.write(f'出力先フォルダ \'{output_root_path}\' を作成しました。')
        except Exception as e:
            messagebox.showerror('エラー', f'出力先フォルダ \'{output_root_path}\' の作成に失敗しました: {e}\nスクリプトを終了します。')
            cleanup_logger() # 終了時にロガーをクリーンアップ
            return

    # ログファイルのパスを決定
    log_filename = f"GooglePhotoOrganizer_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file_path = os.path.join(output_root_path, log_filename)

    # ログ出力先をファイルにも変更
    setup_logger(log_file_path)
    app_logger.write(f"--- ログ出力開始: {log_file_path} ---")


    target_folders_to_process = []
    
    for item_name in os.listdir(takeout_root_path):
        item_path = os.path.join(takeout_root_path, item_name)
        if os.path.isdir(item_path):
            target_folders_to_process.append(item_path)
            app_logger.write(f'対象フォルダとして \'{item_name}\' を追加しました。')
    
    target_folders_to_process.append(takeout_root_path)
    app_logger.write(f'対象フォルダとして \'{os.path.basename(takeout_root_path)}\' (ルートフォルダ内の未分類ファイル) を追加しました。')

    target_folders_to_process = list(set(target_folders_to_process))
    
    if not target_folders_to_process:
        app_logger.write('処理対象となるフォルダ（Google Takeoutルート内のサブフォルダ、またはルート直下のファイル）が見つかりませんでした。')
        app_logger.write('指定されたルートフォルダにメディアファイルが含まれていない可能性があります。')
        messagebox.showinfo(
            '処理完了',
            '処理対象となるフォルダ（Google Takeoutルート内のサブフォルダ、またはルート直下のファイル）が見つかりませんでした。\n'
            '指定されたルートフォルダにメディアファイルが含まれていない可能性があります。',
        )
        cleanup_logger() # 終了時にロガーをクリーンアップ
        return

    confirmation_msg = "「Google Takeout オーガナイザー」は、以下のGoogle Takeoutフォルダ内の動画・写真ファイルを整理し、\n"
    confirmation_msg += f"**指定された出力先フォルダ: \'{os.path.basename(output_root_path)}\'** へコピーを開始します。\n\n"
    confirmation_msg += "**【処理対象フォルダ】**\n"
    
    display_folders = [os.path.basename(f) for f in target_folders_to_process if f != takeout_root_path]
    if takeout_root_path in target_folders_to_process:
        display_folders.insert(0, f"{os.path.basename(takeout_root_path)} (ルート直下ファイル)")

    for folder_name in display_folders:
        confirmation_msg += f"- {folder_name}\n"
    
    confirmation_msg += "\nこの処理はファイルを**コピー**するため、元のGoogle Takeoutデータは変更されません。\n"
    confirmation_msg += "続行しますか？"

    if messagebox.askyesno("処理の確認", confirmation_msg):
        app_logger.write("\n--- メディアファイルの整理処理を開始します ---")
        
        create_progress_window()

        processed, copied_dated, copied_unknown, skipped_existing, failed = process_media_files(
            takeout_root_path, output_root_path, target_folders_to_process, update_progress
        )
        
        destroy_progress_window()

        final_message = (
            f'「Google Takeout オーガナイザー」によるメディアファイルの整理が完了しました！\n\n'
            f'**【処理結果】**\n'
            f'元のGoogle Takeoutから処理したファイル総数: {processed} 件\n'
            f'新しい年/月フォルダにコピーできたファイル数: {copied_dated} 件\n'
            f'「dateunknown」フォルダにコピーしたファイル数: {copied_unknown} 件\n'
            f'出力先に既に存在したためスキップしたファイル数: {skipped_existing} 件\n'
            f'処理に失敗したファイル数: {failed} 件\n\n'
            f'詳細な処理ログは、出力先フォルダ: \'{output_root_path}\' 内のログファイル\n'
            f'\'**{log_filename}**\' をご確認ください。'
        )
        messagebox.showinfo('処理完了', final_message)
        app_logger.write(final_message)
    else:
        app_logger.write('ユーザーによって処理が中断されました。')
        messagebox.showwarning('処理中断', 'ユーザーによって処理が中断されました。')
    
    cleanup_logger() # スクリプト終了前にロガーをクリーンアップ

if __name__ == '__main__':
    main()
