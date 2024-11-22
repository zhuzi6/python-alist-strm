#移除暂停1分钟的逻辑
import sqlite3
import requests
from urllib import parse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import random


class AlistDownload:
    def __init__(self, url, save_path, db_path, max_workers=5):
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

        parseresult = parse.urlparse(url)
        scheme = parseresult.scheme
        netloc = parseresult.netloc
        path = parse.unquote(parseresult.path)

        self.host = f"{scheme}://{netloc}"
        self.save_path = save_path
        self.db_path = db_path

        self.init_db()

        self.processed_paths = self.load_processed_paths()
        self.failed_files = self.load_failed_files()
        self.max_workers = max_workers
        self.start_time = time.time()

        # Retry previously failed files if available
        if self.failed_files:
            print("Retrying failed files from the last session...")
            self.retry_failed_files()

        self.get_list(path)
        print("遍历完成")

    def init_db(self):
        """Initialize the SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_paths (
                path TEXT PRIMARY KEY
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS failed_files (
                dir_path TEXT,
                file_name TEXT,
                url TEXT,
                PRIMARY KEY (dir_path, file_name)
            )
        """)
        self.conn.commit()

    def post(self, url, data) -> (bool, dict):
        req_json = {}
        error_number = 0
        while True:
            try:
                req = requests.post(url=url, json=data, headers=self.headers, timeout=30)
                status_code = req.status_code
                req_json = req.json()
                req.close()
                if status_code == 200:
                    break
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
                error_number += 1
                if error_number > 10:
                    return False, req_json
                time.sleep(2 ** error_number + random.uniform(0, 3))
        return status_code == 200, req_json

    def get_list(self, path):
        if path in self.processed_paths:
            return

        url = self.host + "/api/fs/list"
        data = {"path": path, "password": "", "page": 1, "per_page": 0, "refresh": False}
        file_list = []
        while True:
            req_type, req_json = self.post(url=url, data=data)
            if not req_type:
                return
            if req_json.get("code") == 200:
                break

        content = req_json.get("data", {}).get("content", [])
        for file_info in content:
            if file_info["is_dir"]:
                file_download_url = path + "/" + file_info["name"]
                file_list.append({"is_dir": True, "path": file_download_url})
            else:
                file_download_url = self.host + "/d" + path + "/" + file_info["name"]
                if file_info["name"].lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv')):
                    self.write_strm_file(path, file_info["name"].rsplit('.', 1)[0], file_download_url)
                else:
                    self.download_file(path, file_info["name"], file_download_url)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.get_list, file["path"]) for file in file_list if file["is_dir"]]
            for future in as_completed(futures):
                future.result()

        self.add_processed_path(path)

    def write_strm_file(self, dir_path, file_name, url):
        strm_file_path = os.path.join(self.save_path, dir_path.lstrip('/'), file_name + ".strm")
        os.makedirs(os.path.dirname(strm_file_path), exist_ok=True)
        with open(strm_file_path, 'w', encoding='utf-8') as f:
            f.write(url)

    def download_file(self, dir_path, file_name, url):
        file_path = os.path.join(self.save_path, dir_path.lstrip('/'), file_name)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        error_number = 0
        while True:
            try:
                response = requests.get(url, headers=self.headers, stream=True)
                total_size = int(response.headers.get('content-length', 0))
                with open(file_path, 'wb') as f, tqdm(
                    desc=file_name,
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        bar.update(len(chunk))
                break  # Download succeeded
            except requests.exceptions.RequestException as e:
                print(f"Download failed: {e}")
                error_number += 1
                if error_number > 10:
                    print(f"文件 {file_name} 下载失败超过 10 次，已添加到失败列表。")
                    self.add_failed_file(dir_path, file_name, url)
                    return
                time.sleep(2 ** error_number)

    def load_failed_files(self):
        self.cursor.execute("SELECT dir_path, file_name, url FROM failed_files")
        return [{"dir_path": row[0], "file_name": row[1], "url": row[2]} for row in self.cursor.fetchall()]

    def add_failed_file(self, dir_path, file_name, url):
        try:
            self.cursor.execute("""
                INSERT INTO failed_files (dir_path, file_name, url)
                VALUES (?, ?, ?)
            """, (dir_path, file_name, url))
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # File already exists in the failed list

    def remove_failed_file(self, dir_path, file_name):
        self.cursor.execute("""
            DELETE FROM failed_files WHERE dir_path = ? AND file_name = ?
        """, (dir_path, file_name))
        self.conn.commit()

    def retry_failed_files(self):
        for file in self.failed_files[:]:
            print(f"Retrying file: {file['file_name']}...")
            self.download_file(file["dir_path"], file["file_name"], file["url"])
            self.remove_failed_file(file["dir_path"], file["file_name"])

    def load_processed_paths(self):
        self.cursor.execute("SELECT path FROM processed_paths")
        return {row[0] for row in self.cursor.fetchall()}

    def add_processed_path(self, path):
        try:
            self.cursor.execute("INSERT INTO processed_paths (path) VALUES (?)", (path,))
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass


if __name__ == '__main__':
    alist_url = ""#alist地址
    save_path = ""#下载地址
    db_path = ""#本地数据库地址

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    AlistDownload(alist_url, save_path, db_path)
