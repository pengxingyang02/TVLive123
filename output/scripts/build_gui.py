#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVLive1.1 / TVBox 多版本打包工具
- GUI 弹窗选择/自动检测/联网下载 JDK & Android SDK
- 支持 6 种打包变体: java | java32 | java64 | python | python32 | python64
- 参考 TVBoxOS-main 项目构建体系
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import os
import sys
import re
import json
import queue
import zipfile
import shutil
import ssl
import urllib.request
import urllib.error

VERSION = "2.0.0"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..'))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output', 'apk')
GRADLEW = os.path.join(PROJECT_ROOT, 'gradlew.bat')
CACHE_FILE = os.path.join(SCRIPT_DIR, '.build_cache.json')

JDK_DOWNLOAD_URL = "https://api.adoptium.net/v3/assets/latest/{version}/hotspot?os=windows&architecture=x64&image_type=jdk"
SDK_DOWNLOAD_URL = "https://dl.google.com/android/repository/commandlinetools-win-{version}_latest.zip"
SDK_DEFAULT_VERSION = "11076708"
JDK_DEFAULT = 11

# ---- 版本与变体 ----
ANDROID_VERSIONS = {
    "4.4": {"api": 19, "label": "Android 4.4 (API 19)"},
    "5.0": {"api": 21, "label": "Android 5.0 (API 21)"},
}

VARIANTS = {
    "java32":    {"desc": "Java · 32位 (armeabi-v7a)", "minSdk": 19},
    "java":      {"desc": "Java · 32/64位 (v7a+v8a)", "minSdk": 19},
    "java64":    {"desc": "Java · 64位 (arm64-v8a)", "minSdk": 21},
    "python32":  {"desc": "Python · 32位 (armeabi-v7a)", "minSdk": 19},
    "python":    {"desc": "Python · 32/64位 (v7a+v8a)", "minSdk": 19},
    "python64":  {"desc": "Python · 64位 (arm64-v8a)", "minSdk": 21},
}

DEFAULT_VERSION = "4.4"
DEFAULT_VARIANT = "java32"

# ---- 自动检测 ----
def find_jdk():
    """自动检测 JDK 11+ 路径"""
    candidates = []

    env_home = os.environ.get('JAVA_HOME', '')
    if env_home:
        candidates.append(env_home)

    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\JavaSoft\JDK", r"SOFTWARE\JavaSoft\Java Development Kit"):
                try:
                    key = winreg.OpenKey(root, sub)
                    i = 0
                    while True:
                        try:
                            name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(root, sub + "\\" + name)
                            jh, _ = winreg.QueryValueEx(subkey, "JavaHome")
                            candidates.append(jh)
                            winreg.CloseKey(subkey)
                        except OSError:
                            break
                        i += 1
                    winreg.CloseKey(key)
                except OSError:
                    pass
    except Exception:
        pass

    search_roots = [
        os.environ.get('ProgramFiles', 'C:\\Program Files'),
        os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk'),
        'C:\\Program Files\\Android\\Android Studio\\jbr',
        'C:\\Program Files\\Eclipse Adoptium',
        'C:\\Program Files\\Java',
    ]

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, _ in os.walk(root):
            depth = dirpath.replace(root, '').count(os.sep)
            if depth > 5:
                dirs.clear()
                continue
            if os.path.exists(os.path.join(dirpath, 'bin', 'javac.exe')):
                candidates.append(dirpath)

    seen = set()
    result = []
    for c in candidates:
        c = os.path.normpath(c)
        if c not in seen and os.path.isdir(c):
            release = os.path.join(c, 'release')
            vers = _parse_java_release(release)
            javac = os.path.join(c, 'bin', 'javac.exe')
            java = os.path.join(c, 'bin', 'java.exe')
            if os.path.isfile(javac) and os.path.isfile(java):
                seen.add(c)
                result.append((c, vers or "?"))

    result.sort(key=lambda x: _version_key(x[1]), reverse=True)
    return result


def _parse_java_release(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'JAVA_VERSION="([^"]+)"', line)
                if m:
                    return m.group(1).replace('_', '.')
    except Exception:
        pass
    return None


def _version_key(v):
    try:
        parts = v.split('.')
        return tuple(int(x) for x in parts if x.isdigit())
    except Exception:
        return (-1,)


def find_android_sdk():
    """自动检测 Android SDK 路径"""
    candidates = []
    env_home = os.environ.get('ANDROID_HOME', '')
    if env_home:
        candidates.append(env_home)

    common = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk'),
        os.path.join(os.environ.get('APPDATA', ''), 'Android', 'Sdk'),
        'C:\\Android\\Sdk',
        'D:\\Android\\Sdk',
    ]
    for p in common:
        if p not in candidates:
            candidates.append(p)

    result = []
    seen = set()
    for c in candidates:
        c = os.path.normpath(c)
        if c not in seen and os.path.isdir(c):
            adb = os.path.join(c, 'platform-tools', 'adb.exe')
            sdk_mgr = os.path.join(c, 'cmdline-tools', 'latest', 'bin', 'sdkmanager.bat')
            if os.path.isfile(adb) or os.path.isfile(sdk_mgr):
                seen.add(c)
                build_tools = _find_build_tools(c)
                result.append((c, build_tools))
    return result


def _find_build_tools(sdk_root):
    path = os.path.join(sdk_root, 'build-tools')
    if not os.path.isdir(path):
        return "无"
    vers = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    vers.sort(reverse=True)
    return ", ".join(vers[:3]) if vers else "无"


# ---- 下载模块 ----
def download_jdk(version, dest_parent, progress_cb=None):
    """下载 JDK 到指定目录"""
    os.makedirs(dest_parent, exist_ok=True)
    zip_path = os.path.join(dest_parent, f'jdk-{version}.zip')

    api_url = JDK_DOWNLOAD_URL.format(version=version)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if progress_cb:
        progress_cb(0, "正在查询 JDK 下载地址...")

    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    data = json.loads(resp.read().decode('utf-8'))

    dl_url = data[0]['binaries'][0]['package']['link']
    total_size = data[0]['binaries'][0]['package'].get('size', 0)

    if progress_cb:
        progress_cb(1, f"正在下载 JDK {version} ({total_size//1024//1024}MB)...")

    req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, context=ctx, timeout=600)
    with open(zip_path, 'wb') as f:
        downloaded = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total_size:
                progress_cb(int(100 * downloaded / total_size), f"下载中... {downloaded//1024//1024}MB / {total_size//1024//1024}MB")

    if progress_cb:
        progress_cb(100, "解压中...")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_parent)

    os.remove(zip_path)

    for d in os.listdir(dest_parent):
        full = os.path.join(dest_parent, d)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, 'bin', 'javac.exe')):
            return full
    if os.path.isfile(os.path.join(dest_parent, 'bin', 'javac.exe')):
        return dest_parent
    return None


def download_android_sdk(dest_parent, progress_cb=None):
    """下载 Android SDK 命令行工具"""
    os.makedirs(dest_parent, exist_ok=True)
    cmdline_dir = os.path.join(dest_parent, 'cmdline-tools', 'latest')
    zip_path = os.path.join(dest_parent, 'sdk-tools.zip')

    url = SDK_DOWNLOAD_URL.format(version=SDK_DEFAULT_VERSION)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if progress_cb:
        progress_cb(0, "正在下载 Android SDK 命令行工具...")

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, context=ctx, timeout=600)
        with open(zip_path, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    except Exception:
        alt_url = "https://dl.google.com/android/repository/commandlinetools-win-9477386_latest.zip"
        req = urllib.request.Request(alt_url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, context=ctx, timeout=600)
        with open(zip_path, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)

    if progress_cb:
        progress_cb(80, "解压 SDK 工具...")

    if os.path.exists(cmdline_dir):
        shutil.rmtree(cmdline_dir, ignore_errors=True)
    os.makedirs(cmdline_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = [m for m in zf.namelist() if m.startswith('cmdline-tools/')]
        for member in members:
            target = os.path.join(cmdline_dir, os.path.relpath(member, 'cmdline-tools'))
            if member.endswith('/'):
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as src, open(target, 'wb') as dst:
                    dst.write(src.read())

    os.remove(zip_path)
    os.environ['ANDROID_HOME'] = dest_parent
    return dest_parent


# ---- 缓存 ----
def load_cache():
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ---- 构建执行 ----
class BuildRunner(threading.Thread):
    def __init__(self, jdk_home, sdk_root, variant, build_type, clean_first, android_version, log_cb, done_cb, progress_cb):
        super().__init__(daemon=True)
        self.jdk_home = jdk_home
        self.sdk_root = sdk_root
        self.variant = variant
        self.build_type = build_type
        self.clean_first = clean_first
        self.android_version = android_version
        self.log_cb = log_cb
        self.done_cb = done_cb
        self.progress_cb = progress_cb
        self._cancel = False

    def cancel(self):
        self._cancel = True
        if hasattr(self, '_proc') and self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        env = os.environ.copy()
        env['JAVA_HOME'] = self.jdk_home
        if self.sdk_root:
            env['ANDROID_HOME'] = self.sdk_root
        env['PATH'] = os.pathsep.join([
            os.path.join(self.jdk_home, 'bin'),
            os.path.join(self.sdk_root, 'platform-tools') if self.sdk_root else '',
            env.get('PATH', ''),
        ])

        task = "assemble{}{}".format(
            self.variant[0].upper() + self.variant[1:],
            self.build_type[0].upper() + self.build_type[1:]
        )

        cmds = []
        if self.clean_first:
            cmds.append(('clean', [GRADLEW, 'clean']))
        cmds.append((task, [GRADLEW, task]))

        if self.log_cb:
            self.log_cb("=" * 60, "header")
            self.log_cb(f"TVLive1.1 打包工具 v{VERSION}", "header")
            self.log_cb(f"变体: {self.variant} ({VARIANTS[self.variant]['desc']})", "header")
            self.log_cb(f"类型: {self.build_type}", "header")
            self.log_cb(f"JDK: {self.jdk_home}", "header")
            self.log_cb(f"SDK: {self.sdk_root or '(detect)'}", "header")
            self.log_cb(f"输出: {OUTPUT_DIR}", "header")
            self.log_cb("=" * 60, "header")

        total = len(cmds)
        for idx, (name, cmd) in enumerate(cmds):
            if self._cancel:
                if self.log_cb:
                    self.log_cb("\n[取消] 用户中断", "error")
                self.done_cb(False, "用户取消")
                return

            if self.log_cb:
                self.log_cb(f"\n>>> 执行: {name} ({idx+1}/{total})", "info")

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    cwd=PROJECT_ROOT,
                    bufsize=1,
                )
                self._proc = proc

                q = queue.Queue()

                def _read_stdout():
                    try:
                        for line in iter(proc.stdout.readline, ''):
                            q.put(line)
                    except Exception:
                        pass
                    finally:
                        q.put(None)

                reader = threading.Thread(target=_read_stdout, daemon=True)
                reader.start()

                batch = []

                def _flush():
                    nonlocal batch
                    if batch and self.log_cb:
                        self.log_cb('\n'.join(batch), 'normal')
                        batch = []

                while True:
                    try:
                        line = q.get(timeout=0.3)
                    except queue.Empty:
                        if self._cancel:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            reader.join(timeout=2)
                            _flush()
                            if self.log_cb:
                                self.log_cb("\n[取消] 用户中断", "error")
                            self.done_cb(False, "用户取消")
                            return
                        _flush()
                        continue

                    if line is None:
                        _flush()
                        break

                    line = line.rstrip()
                    if not line:
                        continue

                    tag = "normal"
                    upper = line.upper()
                    if any(k in upper for k in ("ERROR", "FAILED", "EXCEPTION", "BUILD FAILED")):
                        tag = "error"
                    elif any(k in upper for k in ("WARNING", "WARN")):
                        tag = "warning"
                    elif any(k in upper for k in ("SUCCESS", "BUILD SUCCESSFUL")):
                        tag = "success"

                    batch.append(line)
                    if len(batch) >= 20 or tag != "normal":
                        _flush()

                _flush()
                reader.join(timeout=2)
                proc.wait()

                if proc.returncode != 0:
                    if self.log_cb:
                        self.log_cb(f"\n[失败] {name} 返回码: {proc.returncode}", "error")
                    self.done_cb(False, f"{name} 失败 (返回码 {proc.returncode})")
                    return

            except Exception as e:
                if self.log_cb:
                    self.log_cb(f"\n[异常] {e}", "error")
                self.done_cb(False, str(e))
                return

            if self.progress_cb:
                self.progress_cb(int(100 * (idx + 1) / total))

        expected_file = "TVBox_{}-{}_{}.apk".format(self.build_type, self.variant, self.android_version)
        apk_path = os.path.join(OUTPUT_DIR, expected_file)

        if self.log_cb:
            self.log_cb("=" * 60, "header")
            if os.path.isfile(apk_path):
                size_mb = os.path.getsize(apk_path) / 1024 / 1024
                self.log_cb(f"[成功] 打包完成!", "success")
                self.log_cb(f"  文件: {apk_path}", "success")
                self.log_cb(f"  大小: {size_mb:.1f} MB", "success")
            else:
                self.log_cb(f"[注意] APK 未在预期位置: {apk_path}", "warning")
                self.log_cb(f"  请检查 {OUTPUT_DIR} 目录", "warning")
            self.log_cb("=" * 60, "header")

        self.done_cb(True, "打包完成")


# ---- GUI ----
class BuildGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"TVLive1.1 多版本打包工具 v{VERSION}")
        self.geometry("860x720")
        self.minsize(700, 580)
        self.resizable(True, True)

        self.cache = load_cache()
        self.jdk_path = tk.StringVar(value=self.cache.get('jdk_path', ''))
        self.sdk_path = tk.StringVar(value=self.cache.get('sdk_path', ''))
        self.version_var = tk.StringVar(value=self.cache.get('version', DEFAULT_VERSION))
        self.variant_var = tk.StringVar(value=self.cache.get('variant', DEFAULT_VARIANT))
        self.build_type_var = tk.StringVar(value=self.cache.get('build_type', 'release'))
        self.clean_var = tk.BooleanVar(value=False)

        self.runner = None
        self._build_ui()
        self._auto_detect()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== 环境配置 =====
        env_frame = ttk.LabelFrame(main_frame, text="开发环境", padding=8)
        env_frame.pack(fill=tk.X, pady=(0, 8))

        row0 = ttk.Frame(env_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="JDK (Java 开发工具包)", width=24).pack(side=tk.LEFT)
        ttk.Entry(row0, textvariable=self.jdk_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        ttk.Button(row0, text="浏览", width=5, command=self._browse_jdk).pack(side=tk.LEFT, padx=1)
        ttk.Button(row0, text="检测", width=5, command=self._detect_jdk).pack(side=tk.LEFT, padx=1)
        ttk.Button(row0, text="下载JDK11", width=8, command=lambda: self._dl_jdk(11)).pack(side=tk.LEFT, padx=1)

        row1 = ttk.Frame(env_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Android SDK", width=24).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.sdk_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        ttk.Button(row1, text="浏览", width=5, command=self._browse_sdk).pack(side=tk.LEFT, padx=1)
        ttk.Button(row1, text="检测", width=5, command=self._detect_sdk).pack(side=tk.LEFT, padx=1)
        ttk.Button(row1, text="下载SDK", width=8, command=self._dl_sdk).pack(side=tk.LEFT, padx=1)

        status = ttk.Frame(env_frame)
        status.pack(fill=tk.X, pady=(3, 0))
        self.env_status = ttk.Label(status, text="", foreground="gray")
        self.env_status.pack(side=tk.LEFT)

        # ===== 打包选项 =====
        opt_frame = ttk.LabelFrame(main_frame, text="打包选项", padding=8)
        opt_frame.pack(fill=tk.X, pady=(0, 8))

        ver_row = ttk.Frame(opt_frame)
        ver_row.pack(fill=tk.X, pady=2)
        ttk.Label(ver_row, text="Android 版本", width=24).pack(side=tk.LEFT)
        self.version_combo = ttk.Combobox(ver_row, textvariable=self.version_var,
                                           values=list(ANDROID_VERSIONS.keys()), state='readonly', width=10)
        self.version_combo.pack(side=tk.LEFT, padx=3)
        self.version_combo.bind('<<ComboboxSelected>>', lambda e: self._on_version_change())
        self.version_api_label = ttk.Label(ver_row, text="", foreground="gray")
        self.version_api_label.pack(side=tk.LEFT, padx=10)

        var_row = ttk.Frame(opt_frame)
        var_row.pack(fill=tk.X, pady=2)
        ttk.Label(var_row, text="构建变体", width=24).pack(side=tk.LEFT)
        self.variant_combo = ttk.Combobox(var_row, textvariable=self.variant_var,
                                           values=[], state='readonly', width=30)
        self.variant_combo.pack(side=tk.LEFT, padx=3)
        self.variant_combo.bind('<<ComboboxSelected>>', lambda e: self._on_variant_change())
        self.variant_desc = ttk.Label(var_row, text="", foreground="gray")
        self.variant_desc.pack(side=tk.LEFT, padx=10)

        bt_row = ttk.Frame(opt_frame)
        bt_row.pack(fill=tk.X, pady=2)
        ttk.Label(bt_row, text="构建类型", width=24).pack(side=tk.LEFT)
        ttk.Radiobutton(bt_row, text="Release (正式版)", variable=self.build_type_var, value='release').pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(bt_row, text="Debug (调试版)", variable=self.build_type_var, value='debug').pack(side=tk.LEFT, padx=5)

        cl_row = ttk.Frame(opt_frame)
        cl_row.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(cl_row, text="打包前清理 (clean)", variable=self.clean_var).pack(side=tk.LEFT)

        self._on_version_change()

        # ===== 按钮区 =====
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        self.build_btn = ttk.Button(btn_frame, text="开始打包", command=self._start_build)
        self.build_btn.pack(side=tk.LEFT, padx=3)

        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self._cancel_build, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=3)

        ttk.Button(btn_frame, text="打开输出目录", command=self._open_output).pack(side=tk.LEFT, padx=3)

        self.progress = ttk.Progressbar(btn_frame, mode='indeterminate', length=150)
        self.progress.pack(side=tk.RIGHT, padx=3)

        # ===== 日志 =====
        log_frame = ttk.LabelFrame(main_frame, text="构建日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Consolas', 9),
                                                      state=tk.DISABLED, bg='#1e1e1e')
        self.log_widget.pack(fill=tk.BOTH, expand=True)

        self.log_widget.tag_configure('header', foreground='#569cd6', font=('Consolas', 9, 'bold'))
        self.log_widget.tag_configure('error', foreground='#f44747')
        self.log_widget.tag_configure('warning', foreground='#cca700')
        self.log_widget.tag_configure('success', foreground='#6a9955')
        self.log_widget.tag_configure('info', foreground='#4fc1ff')
        self.log_widget.tag_configure('normal', foreground='#d4d4d4')

        # 底部
        bottom = ttk.Frame(main_frame)
        bottom.pack(fill=tk.X, pady=(3, 0))
        self.status_label = ttk.Label(bottom, text="就绪")
        self.status_label.pack(side=tk.LEFT)
        ttk.Label(bottom, text=f"v{VERSION} · 参考 TVBoxOS-main", foreground="gray").pack(side=tk.RIGHT)

    # ---- 自动检测 ----
    def _auto_detect(self):
        if not self.jdk_path.get():
            self._detect_jdk()
        if not self.sdk_path.get():
            self._detect_sdk()

    def _detect_jdk(self):
        self.log("正在检测 JDK...", "info")
        jdks = find_jdk()
        if jdks:
            best = jdks[0]
            self.jdk_path.set(best[0])
            self.env_status.config(text=f"检测到 {len(jdks)} 个 JDK，已选: {best[0]} (v{best[1]})", foreground="green")
            self._save_state()
        else:
            self.env_status.config(text="未检测到 JDK，请手动选择或下载", foreground="red")

    def _detect_sdk(self):
        self.log("正在检测 Android SDK...", "info")
        sdks = find_android_sdk()
        if sdks:
            best = sdks[0]
            self.sdk_path.set(best[0])
            self.env_status.config(text=f"SDK: {best[0]} (build-tools: {best[1]})", foreground="green")
            self._save_state()
        else:
            self.env_status.config(text="未检测到 Android SDK，如已通过 Android Studio 安装则忽略", foreground="orange")

    def _browse_jdk(self):
        p = filedialog.askdirectory(title="选择 JDK 根目录 (包含 bin/javac.exe)")
        if p:
            self.jdk_path.set(p)
            self._save_state()

    def _browse_sdk(self):
        p = filedialog.askdirectory(title="选择 Android SDK 根目录 (包含 platform-tools)")
        if p:
            self.sdk_path.set(p)
            self._save_state()

    # ---- 下载 ----
    def _dl_jdk(self, version):
        if not tk.messagebox.askyesno("确认下载", f"将下载 JDK {version} (约190MB) 到项目 tools 目录。\n继续？"):
            return
        dest = os.path.join(PROJECT_ROOT, 'tools', f'jdk-{version}')
        self._run_download(lambda cb: download_jdk(version, dest, progress_cb=cb),
                           f"JDK {version}", dest)

    def _dl_sdk(self):
        if not tk.messagebox.askyesno("确认下载", "将下载 Android SDK 命令行工具 (约150MB) 到项目 tools 目录。\n继续？"):
            return
        dest = os.path.join(PROJECT_ROOT, 'tools', 'android-sdk')
        self._run_download(lambda cb: download_android_sdk(dest, progress_cb=cb),
                           "Android SDK", dest)

    def _run_download(self, download_fn, name, dest):
        self.build_btn.config(state=tk.DISABLED)
        if name:
            self.status_label.config(text=f"准备下载 {name}...")
        self.progress.config(mode='determinate', maximum=100, value=0)

        def _do():
            try:
                result = download_fn(lambda p, msg: self.after(0, self._on_dl_progress, p, msg))
                self.after(0, self._on_dl_done, result, name, dest)
            except Exception as e:
                self.after(0, self._on_dl_error, str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _on_dl_progress(self, pct, msg):
        self.progress['value'] = pct
        self.status_label.config(text=msg)

    def _on_dl_done(self, result, name, dest):
        self.progress.config(mode='indeterminate')
        self.build_btn.config(state=tk.NORMAL)
        if result:
            if 'jdk' in name.lower():
                self.jdk_path.set(result)
            else:
                self.sdk_path.set(dest)
            self._save_state()
            self.log(f"[下载完成] {name} → {result}", "success")
            self.status_label.config(text=f"{name} 下载完成")
        else:
            self.log(f"[下载失败] {name} 无法定位安装目录", "error")
            self.status_label.config(text="下载失败")

    def _on_dl_error(self, msg):
        self.progress.config(mode='indeterminate')
        self.build_btn.config(state=tk.NORMAL)
        self.log(f"[下载异常] {msg}", "error")
        self.status_label.config(text="下载失败")

    # ---- 变体切换 ----
    def _on_version_change(self, *_):
        ver = self.version_var.get()
        last = self.cache.get('last_version', '')
        if last and last != ver:
            self.clean_var.set(True)
        if ver in ANDROID_VERSIONS:
            api = ANDROID_VERSIONS[ver]["api"]
            self.version_api_label.config(text=f"API {api}")
            allowed = [k for k, v in VARIANTS.items() if v["minSdk"] <= api]
            self.variant_combo['values'] = allowed
            if self.variant_var.get() not in allowed:
                self.variant_var.set(allowed[0] if allowed else "")
        self._update_variant_desc()
        self._save_state()

    def _on_variant_change(self, *_):
        v = self.variant_var.get()
        last = self.cache.get('last_variant', '')
        if last and last != v:
            self.clean_var.set(True)
        self._update_variant_desc()
        self._save_state()

    def _update_variant_desc(self):
        v = self.variant_var.get()
        if v in VARIANTS:
            self.variant_desc.config(text=VARIANTS[v]['desc'])

    # ---- 构建 ----
    def _start_build(self):
        jdk = self.jdk_path.get().strip()
        sdk = self.sdk_path.get().strip()
        version = self.version_var.get()
        variant = self.variant_var.get()
        build_type = self.build_type_var.get()
        clean = self.clean_var.get()

        if not jdk or not os.path.isfile(os.path.join(jdk, 'bin', 'javac.exe')):
            tk.messagebox.showerror("错误", "请先选择有效的 JDK 路径\n(需包含 bin/javac.exe)")
            return

        if not os.path.isfile(GRADLEW):
            tk.messagebox.showerror("错误", f"未找到 gradlew.bat\n预期位置: {GRADLEW}")
            return

        self._save_state()
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete(1.0, tk.END)
        self.log_widget.config(state=tk.DISABLED)

        self.build_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.status_label.config(text="正在打包...")

        self.runner = BuildRunner(
            jdk_home=jdk,
            sdk_root=sdk,
            variant=variant,
            build_type=build_type,
            clean_first=clean,
            android_version='Android{}'.format(version),
            log_cb=self._append_log,
            done_cb=self._on_build_done,
            progress_cb=lambda p: None,
        )
        self.runner.start()

    def _cancel_build(self):
        if self.runner and self.runner.is_alive():
            self.runner.cancel()
            self.status_label.config(text="正在取消...")

    def _on_build_done(self, success, msg):
        self.after(0, lambda: self._finish_build(success, msg))

    def _finish_build(self, success, msg):
        self.progress.stop()
        self.build_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if success:
            self.cache['last_version'] = self.version_var.get()
            self.cache['last_variant'] = self.variant_var.get()
            self.cache['last_build_type'] = self.build_type_var.get()
            save_cache(self.cache)
            self.clean_var.set(False)
            self.status_label.config(text="打包完成！",)
            self._append_log(f"\n打包成功! APK 在: {OUTPUT_DIR}", "success")
        else:
            self.status_label.config(text=f"失败: {msg}")
            self._append_log(f"\n打包失败: {msg}", "error")

    # ---- 日志 ----
    def _append_log(self, text, tag="normal"):
        self.after(0, lambda: self._do_append_log(text, tag))

    def _do_append_log(self, text, tag):
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.insert(tk.END, text + "\n", tag)
        self.log_widget.see(tk.END)
        self.log_widget.config(state=tk.DISABLED)

    def log(self, text, tag="normal"):
        self._do_append_log(text, tag)

    # ---- 工具 ----
    def _save_state(self):
        self.cache['jdk_path'] = self.jdk_path.get()
        self.cache['sdk_path'] = self.sdk_path.get()
        self.cache['version'] = self.version_var.get()
        self.cache['variant'] = self.variant_var.get()
        self.cache['build_type'] = self.build_type_var.get()
        save_cache(self.cache)

    def _open_output(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.startfile(OUTPUT_DIR)


def main():
    app = BuildGUI()
    app.mainloop()


if __name__ == '__main__':
    main()