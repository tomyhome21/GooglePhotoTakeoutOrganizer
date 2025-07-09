import os
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import shutil
import json
import re
from PIL import Image # Pillowライブラリをインポート
from PIL.ExifTags import TAGS, GPSTAGS # EXIFタグの定数をインポート


# Tkinterのルートウィンドウを作成（ユーザーには見えない）
root = tk.Tk()
root.withdraw()  # メインウィンドウを非表示にする


def select_folder(title, initial_dir=None):
    """フォルダ選択ダイアログを開き、選択されたパスを返す"""
    folder_path = filedialog.askdirectory(
        title=title,
        initialdir=initial_dir if initial_dir else os.path.expanduser('~'),
    )
    return folder_path


def set_file_times(file_path, new_timestamp):
    """ファイルの更新日時とアクセス日時を設定する"""
    try:
        os.utime(file_path, (new_timestamp, new_timestamp))
        return True
    except Exception as e:
        print(f'  [エラー] 日時設定失敗 \'{os.path.basename(file_path)}\': {e}')
        return False


def copy_file_to_date_folder(file_path, target_date, output_root_path):
    """ファイルを正しい年/月フォルダにコピーする"""
    try:
        year_folder_path = os.path.join(output_root_path, str(target_date.year))
        month_folder_name = f'{target_date.month:02d}'
        month_folder_path = os.path.join(year_folder_path, month_folder_name)

        os.makedirs(month_folder_path, exist_ok=True)
        destination_path = os.path.join(month_folder_path, os.path.basename(file_path))

        if os.path.exists(destination_path):
            if os.path.getsize(file_path) == os.path.getsize(destination_path):
                print(f'  [スキップ] \'{os.path.basename(file_path)}\' は既に移動先に存在し、内容も同じと判断しました。')
                return False
            else:
                print(f'  [警告] \'{os.path.basename(file_path)}\' は移動先に存在しますが、サイズが異なります。コピーをスキップします。')
                return False
            
        shutil.copy2(file_path, destination_path) # copy2はメタデータもコピー
        # コピー先のファイルのタイムスタンプをJSONまたは取得した日時に設定
        # EXIFから日時を取得した場合は、EXIFの日時で設定される
        if set_file_times(destination_path, target_date.timestamp()):
            print(f'  コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (日時設定済み)')
            return True
        else:
            print(f'  コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (日時設定失敗)')
            return True # コピー自体は成功
    except Exception as e:
        print(
            f'  [エラー] コピー失敗 \'{os.path.basename(file_path)}\' -> \'{month_folder_path}\': {e}'
        )
        return False


def copy_file_to_dateunknown_folder(file_path, output_root_path):
    """ファイルをdateunknownフォルダにコピーする"""
    try:
        dateunknown_folder_path = os.path.join(output_root_path, 'dateunknown')
        os.makedirs(dateunknown_folder_path, exist_ok=True)
        destination_path = os.path.join(dateunknown_folder_path, os.path.basename(file_path))

        if os.path.exists(destination_path):
            if os.path.getsize(file_path) == os.path.getsize(destination_path):
                print(f'  [スキップ] \'{os.path.basename(file_path)}\' は既にdateunknownに存在し、内容も同じと判断しました。')
                return False
            else:
                print(f'  [警告] \'{os.path.basename(file_path)}\' はdateunknownに存在しますが、サイズが異なります。コピーをスキップします。')
                return False

        shutil.copy2(file_path, destination_path) # copy2はメタデータもコピー
        print(f'  コピー成功: \'{os.path.basename(file_path)}\' -> \'{destination_path}\' (dateunknown)')
        return True
    except Exception as e:
        print(
            f'  [エラー] dateunknownへのコピー失敗 \'{os.path.basename(file_path)}\': {e}'
        )
        return False


def get_json_metadata_path(media_path, takeout_root_path):
    """
    メディアファイルに対応するJSONメタデータファイルのパスを推測して返す。
    JSONファイルはメディアファイルと同じディレクトリ、またはGoogle Takeoutのルートディレクトリ以下で
    media_filename.json または media_filename.supplemental-metadata.json の形式で存在しうる。
    """
    media_filename = os.path.basename(media_path)
    media_filename_without_ext = os.path.splitext(media_filename)[0]

    # 検索するJSONファイル名のパターンリスト
    json_name_patterns = [
        media_filename + '.json',
        media_filename_without_ext + '.json',
        media_filename + '.supplemental-metadata.json',
        media_filename_without_ext + '.supplemental-metadata.json'
    ]

    # 1. メディアファイルと同じディレクトリをまず確認
    for pattern in json_name_patterns:
        json_path_same_dir = os.path.join(os.path.dirname(media_path), pattern)
        if os.path.exists(json_path_same_dir):
            return json_path_same_dir
    
    # 2. Google Takeoutのルートディレクトリ以下全体を検索
    # 大量のファイルがある場合、この処理には時間がかかる可能性があります。
    for root_dir, _, files in os.walk(takeout_root_path):
        for file_in_dir in files:
            if file_in_dir in json_name_patterns:
                json_candidate_path = os.path.join(root_dir, file_in_dir)
                if os.path.exists(json_candidate_path):
                    return json_candidate_path
    
    return None


def parse_japanese_date(date_string):
    """
    日本語の日付文字列（例: '2023年10月27日 午後 3:30:00 UTC'）を解析し、datetimeオブジェクトを返す。
    一般的な年/月/日、時:分:秒、タイムゾーン形式を想定。
    """
    # タイムゾーンの調整マップ
    tz_map = {
        'JST': datetime.timezone(datetime.timedelta(hours=9)),
        'UTC': datetime.timezone.utc,
        'GMT': datetime.timezone.utc, # GMTもUTCとして扱う
        'PST': datetime.timezone(datetime.timedelta(hours=-8)), # 例
        'PDT': datetime.timezone(datetime.timedelta(hours=-7)), # 例
    }

    # 日本語の月名、午前/午後を変換
    date_string = date_string.replace('年', '-').replace('月', '-').replace('日', '')
    date_string = date_string.replace('午前', 'AM').replace('午後', 'PM')
    
    # 正規表現でパターンを抽出 (例: '2023-10-27 3:30:00 PM UTC')
    match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})\s*(?:(\d{1,2}:\d{2}:\d{2})\s*(AM|PM)?)?\s*([A-Z]{2,5})?', date_string, re.IGNORECASE)

    if match:
        date_part = match.group(1)
        time_part = match.group(2)
        ampm_part = match.group(3)
        tz_part = match.group(4)

        time_str = ""
        if time_part:
            time_str = f"{time_part}{' ' + ampm_part if ampm_part else ''}"
        
        # 日付と時刻のフォーマット文字列を決定
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

            # タイムゾーン情報を付加
            if tz_part and tz_part.upper() in tz_map:
                dt_obj = dt_obj.replace(tzinfo=tz_map[tz_part.upper()])
            elif tz_part: # 未知のタイムゾーンの場合、UTCとして処理
                print(f"  [警告] 未知のタイムゾーン '{tz_part}' が検出されました。UTCとして処理します。")
                dt_obj = dt_obj.replace(tzinfo=datetime.timezone.utc)
            else: # タイムゾーン情報がない場合、ローカルタイムゾーンとして解釈
                dt_obj = dt_obj.astimezone() # システムのローカルタイムゾーンに変換

            return dt_obj

        except ValueError:
            pass # 解析失敗
    return None


def get_date_from_json(json_file_path):
    """JSONファイルからphotoTakenTimeまたはcreationTimeのUNIXタイムスタンプ/formattedを抽出する"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            
            # 優先度1: photoTakenTime.timestamp (Unixタイムスタンプ)
            if 'photoTakenTime' in json_data and 'timestamp' in json_data['photoTakenTime']:
                try:
                    timestamp_unix = int(json_data['photoTakenTime']['timestamp'])
                    # UTCのタイムスタンプから datetime オブジェクトを生成し、PCのローカルタイムゾーンに変換
                    return datetime.datetime.fromtimestamp(timestamp_unix, tz=datetime.timezone.utc).astimezone()
                except (ValueError, TypeError):
                    pass # 解析失敗したら次へ

            # 優先度2: creationTime.timestamp (Unixタイムスタンプ)
            elif 'creationTime' in json_data and 'timestamp' in json_data['creationTime']:
                try:
                    timestamp_unix = int(json_data['creationTime']['timestamp'])
                    # UTCのタイムスタンプから datetime オブジェクトを生成し、PCのローカルタイムゾーンに変換
                    return datetime.datetime.fromtimestamp(timestamp_unix, tz=datetime.timezone.utc).astimezone()
                except (ValueError, TypeError):
                    pass # 解析失敗したら次へ

            # 優先度3: photoTakenTime.formatted (日付文字列 - 日本語対応)
            if 'photoTakenTime' in json_data and 'formatted' in json_data['photoTakenTime']:
                formatted_date_str = json_data['photoTakenTime']['formatted']
                parsed_dt = parse_japanese_date(formatted_date_str)
                if parsed_dt:
                    return parsed_dt

            # 優先度4: creationTime.formatted (日付文字列 - 日本語対応)
            elif 'creationTime' in json_data and 'formatted' in json_data['creationTime']:
                formatted_date_str = json_data['creationTime']['formatted']
                parsed_dt = parse_japanese_date(formatted_date_str)
                if parsed_dt:
                    return parsed_dt
            
            return None # どちらも見つからない場合

    except (json.JSONDecodeError, FileNotFoundError, KeyError, TypeError) as e:
        print(f'  [警告] JSONファイル \'{os.path.basename(json_file_path)}\' の解析に失敗しました: {e}')
        return None


def get_date_from_exif(file_path):
    """画像ファイルのEXIF情報から撮影日時を取得する"""
    try:
        # 動画ファイルはEXIFを持たないか、信頼性が低いため、画像ファイルのみを対象
        if not file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.heic')):
            return None
            
        with Image.open(file_path) as img:
            exif_data = img._getexif() # _getexif() は非公開APIだが、EXIF読み取りに便利

            if exif_data is None:
                return None

            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                # DateTimeOriginal (オリジナル撮影日時) または DateTimeDigitized (デジタルデータ作成日時) を優先
                if tag_name in ('DateTimeOriginal', 'DateTimeDigitized'):
                    try:
                        # EXIFのタイムスタンプ形式は 'YYYY:MM:DD HH:MM:SS'
                        dt_obj = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                        # EXIFにはタイムゾーン情報がないことが多いので、システムのローカルタイムゾーンとして解釈
                        return dt_obj.astimezone()  
                    except ValueError:
                        pass # フォーマットが異なる場合はスキップ

            # DateTime (ファイルの最終更新日時だが、撮影日であることも)
            if 'DateTime' in TAGS: # 'DateTime' のIDを取得
                tag_id = next((k for k, v in TAGS.items() if v == 'DateTime'), None)
                if tag_id and tag_id in exif_data:
                    try:
                        dt_obj = datetime.datetime.strptime(exif_data[tag_id], '%Y:%m:%d %H:%M:%S')
                        return dt_obj.astimezone()
                    except ValueError:
                        pass

    except Exception as e:
        # EXIFがない、ファイルが破損している、サポートされていない形式など
        print(f'  [警告] EXIF情報からの日時取得に失敗しました \'{os.path.basename(file_path)}\': {e}')
    return None


def is_after_google_photos_release(target_datetime):
    """指定された日時がGoogleフォトのサービス開始日以降であるかを判定する"""
    # Googleフォトのリリース日 (2015年5月28日)
    google_photos_release_date = datetime.datetime(2015, 5, 28, 0, 0, 0)
    
    # target_datetimeがawareな場合とnaiveな場合に対応
    # 比較のため、google_photos_release_dateもawareなdatetimeに変換する
    if target_datetime.tzinfo is not None and target_datetime.tzinfo.utcoffset(target_datetime) is not None:
        # target_datetimeがタイムゾーン情報を持つ場合、リリース日も同じタイムゾーンに変換
        google_photos_release_date_aware = google_photos_release_date.replace(tzinfo=datetime.timezone.utc).astimezone(target_datetime.tzinfo)
    else:
        # target_datetimeがタイムゾーン情報を持たない場合、リリース日もnaiveとして扱う
        google_photos_release_date_aware = google_photos_release_date # Naiveのまま

    now_aware = datetime.datetime.now(target_datetime.tzinfo) if target_datetime.tzinfo is not None else datetime.datetime.now()
    
    # Googleフォトのリリース日以降 かつ 現在日時以前 のファイルを対象とする
    return google_photos_release_date_aware <= target_datetime <= now_aware


def process_media_files(takeout_root_path, output_root_path, target_folders_to_process):
    """指定されたフォルダ内の動画・写真ファイルを処理し、指定された出力フォルダにコピーする"""
    total_processed_files = [0]
    total_copied_to_dated_folders = [0]
    total_copied_to_dateunknown = [0]
    total_skipped_existing_files = [0] # 既存でスキップしたファイル
    total_failed_files = [0]

    media_extensions = ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.jpg', '.jpeg', '.png', '.heic', '.webp', '.gif')

    for folder_path_to_process in target_folders_to_process:
        print(f'--- フォルダ \'{os.path.basename(folder_path_to_process)}\' を処理中 ---')
        for root_dir, _, files in os.walk(folder_path_to_process):
            for file in files:
                if file.lower().endswith(media_extensions):
                    file_full_path = os.path.join(root_dir, file)
                    total_processed_files[0] += 1
                    
                    target_datetime = None
                    copy_to_dateunknown_flag = False # dateunknownへコピーすべきかどうかのフラグ

                    # 1. JSONメタデータから日時を取得
                    json_metadata_path = get_json_metadata_path(file_full_path, takeout_root_path)
                    if json_metadata_path:
                        target_datetime = get_date_from_json(json_metadata_path)
                        if target_datetime:
                            print(f'  JSONから日時取得: \'{os.path.basename(file_full_path)}\' -> {target_datetime.strftime('%Y/%m/%d %H:%M:%S %Z%z')}')
                            
                            # JSONから読み取った日時がGoogleフォトリリース日以降かチェック
                            if not is_after_google_photos_release(target_datetime):
                                print(f'  [情報] JSONの日時がGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象: \'{os.path.basename(file_full_path)}\'')
                                copy_to_dateunknown_flag = True
                        else:
                            print(f'  [警告] JSONから有効な日時情報を取得できませんでした: \'{os.path.basename(json_metadata_path)}\'. 次の取得方法を試行。')
                            # ここではまだdateunknownフラグを立てず、次のEXIFを試す
                    else:
                        print(f'  [情報] 対応するJSONファイルが見つかりませんでした: \'{os.path.basename(file_full_path)}\'. 次の取得方法を試行。')
                        # ここではまだdateunknownフラグを立てず、次のEXIFを試す

                    # 2. JSONから取得できなかった場合、EXIF情報から日時を取得
                    if target_datetime is None:
                        target_datetime = get_date_from_exif(file_full_path)
                        if target_datetime:
                            print(f'  EXIFから日時取得: \'{os.path.basename(file_full_path)}\' -> {target_datetime.strftime('%Y/%m/%d %H:%M:%S')}')
                            if not is_after_google_photos_release(target_datetime):
                                print(f'  [情報] EXIFの日時がGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象: \'{os.path.basename(file_full_path)}\'')
                                copy_to_dateunknown_flag = True
                            else:
                                copy_to_dateunknown_flag = False # EXIFで有効な日時が取得できたのでフラグを解除
                        else:
                            print(f'  [警告] EXIFから有効な日時情報を取得できませんでした: \'{os.path.basename(file_full_path)}\'. 次の取得方法を試行。')
                            # ここでもまだdateunknownフラグを立てず、次のファイルシステムを試す

                    # 3. EXIFからも取得できなかった場合、ファイルシステムの更新日時を代替として使用
                    if target_datetime is None:
                        try:
                            current_file_mod_time_timestamp = os.path.getmtime(file_full_path)
                            target_datetime = datetime.datetime.fromtimestamp(current_file_mod_time_timestamp).astimezone()  
                            print(f'  ファイルシステムの更新日時を使用: \'{os.path.basename(file_full_path)}\' -> {target_datetime.strftime('%Y/%m/%d %H:%M:%S')}')
                            
                            # ファイルシステムの日時もGoogleフォトリリース日より前か未来の場合は、最終的にdateunknownへ
                            if not is_after_google_photos_release(target_datetime):
                                print(f'  [情報] ファイルシステムの日時もGoogleフォトリリース日より前か未来のため、dateunknownへコピー対象: \'{os.path.basename(file_full_path)}\'')
                                copy_to_dateunknown_flag = True
                            else:
                                copy_to_dateunknown_flag = False  
                        except Exception as e:
                            print(f'  [エラー] ファイルシステムの日時取得にも失敗しました \'{os.path.basename(file_full_path)}\': {e}')
                            total_failed_files[0] += 1
                            continue # このファイルの処理をスキップ
                    
                    # 日時が最終的に確定しなかった場合、またはcopy_to_dateunknown_flagが立っている場合
                    if target_datetime is None or copy_to_dateunknown_flag:
                        if copy_file_to_dateunknown_folder(file_full_path, output_root_path):
                            total_copied_to_dateunknown[0] += 1
                        else:
                            if os.path.exists(os.path.join(output_root_path, 'dateunknown', os.path.basename(file_full_path))):
                                total_skipped_existing_files[0] += 1
                            else:
                                total_failed_files[0] += 1
                    else:
                        # 適切な年/月フォルダへコピー
                        if copy_file_to_date_folder(
                            file_full_path, target_datetime, output_root_path
                        ):
                            total_copied_to_dated_folders[0] += 1
                        else:
                            if os.path.exists(os.path.join(output_root_path, str(target_datetime.year), f'{target_datetime.month:02d}', os.path.basename(file_full_path))):
                                total_skipped_existing_files[0] += 1
                            else:
                                total_failed_files[0] += 1

    return (
        total_processed_files[0],
        total_copied_to_dated_folders[0],
        total_copied_to_dateunknown[0],
        total_skipped_existing_files[0],
        total_failed_files[0],
    )


# --- メイン処理の実行部分 ---
if __name__ == '__main__':
    messagebox.showinfo(
        'スクリプト開始: Google Takeout オーガナイザー (EXIF対応版)',
        '「Google Takeout オーガナイザー」へようこそ！\n\n'
        'このスクリプトは、Google Takeoutで展開されたデータのルートフォルダを選択し、'
        'その中の**全ての動画ファイルと写真ファイルを対象**に整理を行います。\n\n'
        '**【重要：事前の準備】**\n'
        '**EXIF情報から日時を取得するためには、Pythonの`Pillow`ライブラリが必要です。**\n'
        'コマンドプロンプトやターミナルで、以下のコマンドを実行してインストールしてください。\n'
        '`pip install Pillow`\n\n'
        '**【重要：スクリプトの動作】**\n'
        '本ツールは、**元のGoogle Takeoutデータは一切変更しません**。\n'
        '整理されたファイルは、後ほど指定していただく**新しい出力先フォルダ**の中に、'
        '`YYYY/MM`形式のフォルダ構造と「`dateunknown`」フォルダでコピーされます。\n\n'
        'もし撮影日時が**Googleフォトのサービス開始（2015年5月28日）より古いファイル、未来のファイル、または日時が特定できないファイル**は、'
        '全て「**dateunknown**」フォルダにコピーされます。\n\n'
        '続行するには、「OK」をクリックしてGoogle Takeoutのルートフォルダを選択してください。'
    )
    takeout_root_path = select_folder('Google Takeoutのルートフォルダを選択 (元のデータ)')

    if not takeout_root_path:
        messagebox.showwarning('処理中断', 'Google Takeoutのルートフォルダが選択されませんでした。スクリプトを終了します。')
    else:
        messagebox.showinfo(
            '出力先フォルダの選択',
            '次に、整理されたファイルがコピーされる新しい出力先フォルダを選択してください。\n'
            '既存のフォルダを選択しても構いませんし、新しいフォルダを作成しても構いません。\n'
            'このフォルダの中に、整理された年/月フォルダと「dateunknown」フォルダが作成されます。'
        )
        output_root_path = select_folder('整理ファイルの出力先フォルダを選択 (新規または既存)')

        if not output_root_path:
            messagebox.showwarning('処理中断', '出力先フォルダが選択されませんでした。スクリプトを終了します。')
        else:
            if not os.path.exists(output_root_path):
                try:
                    os.makedirs(output_root_path)
                    print(f'出力先フォルダ \'{output_root_path}\' を作成しました。')
                except Exception as e:
                    messagebox.showerror('エラー', f'出力先フォルダ \'{output_root_path}\' の作成に失敗しました: {e}\nスクリプトを終了します。')
                    exit()

            target_folders_to_process = []
            
            # Google Takeoutルート直下の全てのサブフォルダを対象にする
            for item_name in os.listdir(takeout_root_path):
                item_path = os.path.join(takeout_root_path, item_name)
                if os.path.isdir(item_path):
                    target_folders_to_process.append(item_path)
                    print(f'対象フォルダとして \'{item_name}\' を追加しました。')
            
            # Google Takeoutルート直下の未分類ファイルも対象にするために、ルート自体も追加
            target_folders_to_process.append(takeout_root_path)
            print(f'対象フォルダとして \'{os.path.basename(takeout_root_path)}\' (ルートフォルダ内の未分類ファイル) を追加しました。')

            # 重複するパスを除去 (念のため)
            target_folders_to_process = list(set(target_folders_to_process))
            
            if not target_folders_to_process:
                messagebox.showinfo(
                    '処理完了',
                    '処理対象となるフォルダ（Google Takeoutルート内のサブフォルダ、またはルート直下のファイル）が見つかりませんでした。\n'
                    '指定されたルートフォルダにメディアファイルが含まれていない可能性があります。',
                )
            else:
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
                    print("\n--- メディアファイルの整理処理を開始します ---")
                    processed, copied_dated, copied_unknown, skipped_existing, failed = process_media_files(
                        takeout_root_path, output_root_path, target_folders_to_process
                    )

                    messagebox.showinfo(
                        '処理完了',
                        f'「Google Takeout オーガナイザー」によるメディアファイルの整理が完了しました！\n\n'
                        f'**【処理結果】**\n'
                        f'元のGoogle Takeoutから処理したファイル総数: {processed} 件\n'
                        f'新しい年/月フォルダにコピーできたファイル数: {copied_dated} 件\n'
                        f'「dateunknown」フォルダにコピーしたファイル数: {copied_unknown} 件\n'
                        f'出力先に既に存在したためスキップしたファイル数: {skipped_existing} 件\n'
                        f'処理に失敗したファイル数: {failed} 件\n\n'
                        f'※ 失敗したファイルがないか、コマンドプロンプト（ターミナル）の出力を確認してください。\n'
                        f'整理されたファイルは、指定された出力先フォルダ: \'{output_root_path}\' にあります。',
                    )
                else:
                    messagebox.showwarning('処理中断', 'ユーザーによって処理が中断されました。')