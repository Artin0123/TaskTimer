import os
import sys
import json
import time
import re
import webbrowser

from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from winotify import Notification, audio
import threading
import ctypes

APP_NAME = "TaskTimer"

# 在打包(exe)與直跑(py)時使用不同基準路徑

def _app_base_dir() -> Path:
    # PyInstaller 打包時會有 sys.frozen 屬性
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

DATA_DIR = Path.home() / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
TASK_FILE = DATA_DIR / "tasks.json"
# 設定檔：
# - 直跑 .py：與 TaskTimer.py 同資料夾 TaskTimer.json
# - 打包 .exe：與 .exe 同資料夾 TaskTimer.json
if getattr(sys, "frozen", False):
    SETTINGS_FILE = _app_base_dir() / "TaskTimer.json"
else:
    SETTINGS_FILE = Path(__file__).resolve().with_suffix(".json")

# 視窗尺寸與時間單位常數
MAIN_WINDOW_WIDTH = 800
MAIN_WINDOW_HEIGHT = 400
TOAST_WINDOW_WIDTH = 360
TOAST_WINDOW_HEIGHT = 100

TIME_UNITS = [
    ("秒", 1),
    ("分", 60),
    ("時", 3600),
    ("天", 86400),
]

def win_toast(title: str, message: str) -> bool:
    # 系統通知，僅顯示
    try:
        toast = Notification(app_id=APP_NAME, title=title, msg=message)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return True
    except Exception:
        return False

@dataclass
class Task:
    id: str
    name: str
    seconds: int
    remaining: int
    is_running: bool = False
    due_at: int | None = None  # 目標時間 unix ts（秒）
    notified: bool = False
    description: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Task":
        return Task(
            id=d.get("id", str(time.time_ns())),
            name=d.get("name", "未命名"),
            seconds=int(d.get("seconds", 0)),
            remaining=int(d.get("remaining", d.get("seconds", 0))),
            is_running=bool(d.get("is_running", False)),
            due_at=(int(d["due_at"]) if d.get("due_at")
                    not in (None, "") else None),
            notified=bool(d.get("notified", False)),
            description=str(d.get("description", "")),
        )

def format_seconds(s: int) -> str:
    s = max(0, int(s))
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    units = [("天", d), ("時", h), ("分", m), ("秒", s)]
    nonzero = [(name, val) for name, val in units if val]
    if not nonzero:
        return "0秒"
    top2 = nonzero[:2]
    return " ".join(f"{val}{name}" for name, val in top2)

class TaskRow(ctk.CTkFrame):
    def __init__(self, master, task: Task, on_action):
        super().__init__(master)
        self.task = task
        self.on_action = on_action  # callback(action, task_id)

        # 佈局欄寬
        # 固定各欄最小寬度，確保文字對齊
        self.grid_columnconfigure(0, weight=0, minsize=160)  # 名稱固定寬
        self.grid_columnconfigure(1, weight=0, minsize=300)  # 目標
        self.grid_columnconfigure(2, weight=0, minsize=60)  # 狀態
        self.grid_columnconfigure(3, weight=1)               # 按鈕區彈性

        # 獲取主程式的字體設定
        try:
            main_app = self.master.master  # 假設是App的子元件
            if hasattr(main_app, 'font_normal'):
                font_normal = main_app.font_normal
            else:
                font_normal = ("Microsoft YaHei", 14)
        except Exception:
            font_normal = ("Arial", 14)

        # 文字欄位（全部靠左）
        self.name_lbl = ctk.CTkLabel(
            self, text=task.name, anchor="w", font=font_normal)
        self.info_lbl = ctk.CTkLabel(
            self, text=self._info_text(task), anchor="w", font=font_normal)
        self.state_lbl = ctk.CTkLabel(
            self, text=self._state_text(task), anchor="w", font=font_normal)
        self.name_lbl.grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.info_lbl.grid(row=0, column=1, sticky="w", padx=6)
        self.state_lbl.grid(row=0, column=2, sticky="w", padx=6)

        # 按鈕列
        btns = ctk.CTkFrame(self)
        btns.grid(row=0, column=3, sticky="e")
        ctk.CTkButton(btns, text="開始", width=48, font=font_normal, command=lambda: self.on_action(
            "start", task.id)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="暫停", width=48, font=font_normal, command=lambda: self.on_action(
            "stop", task.id)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="重設", width=48, font=font_normal, command=lambda: self.on_action(
            "reset", task.id)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="編輯", width=48, font=font_normal, command=lambda: self.on_action(
            "edit", task.id)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="刪除", width=48, font=font_normal, fg_color="#b3261e", command=lambda: self.on_action(
            "delete", task.id)).pack(side="left", padx=2)

    def _info_text(self, task: Task) -> str:
        parts: list[str] = []
        if task.due_at:
            parts.append(time.strftime("%m/%d, %H:%M:%S",
                         time.localtime(task.due_at)))
            if task.is_running:
                remain = max(0, int(task.due_at) - int(time.time()))
                parts.append(f"剩餘 {format_seconds(remain)}")
        else:
            parts.append("目標：未排程")
        return " ".join([p for p in parts if p])

    def _state_text(self, task: Task) -> str:
        if task.due_at and int(time.time()) > int(task.due_at):
            return "超過目標時間"
        return ("進行中" if task.is_running else "已暫停")

    def refresh(self, task: Task):
        self.task = task
        self.name_lbl.configure(text=task.name)
        self.info_lbl.configure(text=self._info_text(task))
        self.state_lbl.configure(text=self._state_text(task))

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)

        try:
            # 最小尺寸固定為800x400
            self.minsize(800, 400)
        except Exception:
            pass

        self.geometry(f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}")

        # 先載入設定，以便初始化主題
        self.settings = self._load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "System"))
        ctk.set_default_color_theme("blue")

        # 設置微軟雅黑為程式字體
        self._setup_fonts()

        # 創建常用字體設定（最小14，大字體16）
        self.font_normal = (self.preferred_font, 14)
        self.font_bold = (self.preferred_font, 14, "bold")
        self.font_large = (self.preferred_font, 16)

        # 托盤相關欄位
        self._tray_icon = None
        self._tray_ready = False
        self._pystray = None
        self._PIL_Image = None
        self._PIL_ImageDraw = None

        # 載入資料與建構 UI
        self.tasks: list[Task] = load_tasks()
        self._build_ui()

        # 視窗置中
        self._apply_window_position()

        # 啟動即建立系統托盤（保持常駐）
        try:
            self._show_tray(minimize_if_missing=False)
        except Exception:
            pass
        # 啟動時最小化至托盤（不顯示主視窗）
        try:
            if bool(self.settings.get("start_minimized_to_tray", False)):
                self.withdraw()
        except Exception:
            pass

        self._start_tick()
        # 關閉視窗改成縮到系統托盤
        try:
            self.protocol("WM_DELETE_WINDOW", self.on_close)
        except Exception:
            pass
        # 補發過期的目標時間通知（若未通知）
        now = int(time.time())
        changed = False
        for t in self.tasks:
            if t.due_at and (not t.notified) and now >= t.due_at:
                # 一定顯示應用通知；系統通知視設定而定
                self._show_in_app_toast(
                    "時間到", f"{t.name} 已到目標時間（點擊開啟編輯）", t.id)
                if bool(self.settings.get("enable_system_notification", True)):
                    win_toast("時間到", f"{t.name} 已到目標時間")
                t.notified = True
                t.is_running = False
                changed = True
        if changed:
            save_tasks(self.tasks)
            self.refresh_rows(full=False)

    def show_and_focus(self):
        try:
            self.deiconify()
            self.after(10, self.lift)
            self.after(20, lambda: self.focus_force())
        except Exception:
            pass

    # --- 輕量 in-app 提示（通知氣泡）---
    def _show_in_app_toast(self, title: str, message: str, task_id: str | None = None):
        try:
            # 若已有舊的提示視窗，先關閉
            if hasattr(self, "_toast_win") and self._toast_win is not None:
                try:
                    self._toast_win.destroy()
                except Exception:
                    pass
                self._toast_win = None

            w = ctk.CTkToplevel(self)
            w.overrideredirect(True)
            w.attributes("-topmost", True)

            frame = ctk.CTkFrame(w)
            frame.pack(fill="both", expand=True)
            ctk.CTkLabel(frame, text=title, font=self.font_bold).pack(
                anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(frame, text=message, font=self.font_normal).pack(
                anchor="w", padx=12, pady=(2, 10))

            # 定位
            try:
                x_txt = str(self.settings.get("toast_x", ""))
                y_txt = str(self.settings.get("toast_y", ""))
                if re.fullmatch(r"-?\d+", x_txt or "") and re.fullmatch(r"-?\d+", y_txt or ""):
                    x = int(x_txt)
                    y = int(y_txt)
                else:
                    physical_w, physical_h, scaling = self._get_screen_info_and_scaling()
                    actual_w = int(TOAST_WINDOW_WIDTH * scaling)
                    actual_h = int(TOAST_WINDOW_HEIGHT * scaling)
                    x = (physical_w - actual_w) // 2
                    y = int(physical_h * 0.75 - actual_h / 2)
                w.geometry(
                    f"{TOAST_WINDOW_WIDTH}x{TOAST_WINDOW_HEIGHT}+{x}+{y}")
            except Exception:
                w.geometry(f"{TOAST_WINDOW_WIDTH}x{TOAST_WINDOW_HEIGHT}")

            self._toast_win = w

            def _open_edit(_evt=None):
                try:
                    self.show_and_focus()
                    if task_id:
                        self.open_edit_overlay(task_id)
                finally:
                    try:
                        w.destroy()
                    except Exception:
                        pass

            # 綁定點擊關聯
            w.bind("<Button-1>", _open_edit)
            for child in frame.winfo_children():
                child.bind("<Button-1>", _open_edit)
        except Exception:
            pass

    def _build_ui(self):
        # 工具列
        toolbar = ctk.CTkFrame(self)
        toolbar.pack(fill="x", padx=8, pady=8)

        ctk.CTkButton(toolbar, text="新增", width=64, font=self.font_normal,
                      command=self.on_add_task).pack(side="left", padx=(0, 8))
        ctk.CTkButton(toolbar, text="設定", width=64, font=self.font_normal,
                      command=self.open_settings_overlay).pack(side="left")
        ctk.CTkButton(toolbar, text="匯出", width=64, font=self.font_normal, command=self.on_export).pack(
            side="left", padx=(8, 0))
        ctk.CTkButton(toolbar, text="匯入", width=64, font=self.font_normal, command=self.on_import).pack(
            side="left", padx=(8, 0))

        # 主內容容器（可在列表 / 編輯間切換）
        self.content = ctk.CTkFrame(self)
        self.content.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # 列表區
        self.scroll = ctk.CTkScrollableFrame(self.content)
        self.scroll.pack(fill="both", expand=True)
        self.row_widgets: dict[str, TaskRow] = {}
        self.refresh_rows(full=True)

        # 內嵌編輯與提示
        self._edit_win: ctk.CTkToplevel | None = None
        self._edit_task_id: str | None = None
        self._toast_win: ctk.CTkToplevel | None = None
        self._settings_win: ctk.CTkToplevel | None = None

    def _setup_fonts(self):
        """設置程式字體為微軟雅黑，提供備選方案"""
        # 先給定一個預設值
        self.preferred_font = "TkDefaultFont"

        try:
            import tkinter.font as tkFont
            available_fonts = tkFont.families()

            # 字體優先順序列表
            font_candidates = [
                "Microsoft YaHei",
                "微軟雅黑",
                "SimHei",
                "Helvetica",
                "Arial"
            ]

            # 找到第一個可用的字體
            for font_name in font_candidates:
                if font_name in available_fonts:
                    self.preferred_font = font_name
                    break

            print(f"最終選擇的字體是: {self.preferred_font}")

        except Exception as e:
            print(f"尋找字體時發生錯誤: {e}")
            self.preferred_font = "TkDefaultFont"

    def _get_screen_info_and_scaling(self):
        """獲取螢幕資訊和DPI縮放係數"""
        self.update_idletasks()

        # 獲取tkinter報告的螢幕尺寸（邏輯像素）
        logical_screen_w = self.winfo_screenwidth()
        logical_screen_h = self.winfo_screenheight()

        # 動態獲取物理螢幕解析度
        try:
            # 使用Windows API獲取真實螢幕解析度
            user32 = ctypes.windll.user32
            physical_screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            physical_screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        except Exception:
            # 備用方案：假設邏輯解析度就是物理解析度（100%縮放）
            physical_screen_w = logical_screen_w
            physical_screen_h = logical_screen_h

        # 計算DPI縮放係數
        scaling_factor = physical_screen_w / \
            logical_screen_w if logical_screen_w > 0 else 1.0

        return physical_screen_w, physical_screen_h, scaling_factor

    def _apply_window_position(self):
        try:
            # 優先使用儲存的位置
            st = self.settings or {}
            x = st.get("win_x")
            y = st.get("win_y")
            w = st.get("win_w")
            h = st.get("win_h")
            if all(v is not None and v != "" for v in [w, h, x, y]):
                self.geometry(f"{w}x{h}+{x}+{y}")
                return

            # 正確的DPI感知置中邏輯
            physical_w, physical_h, scaling = self._get_screen_info_and_scaling()

            # 視窗實際顯示大小 = 邏輯大小 × DPI縮放係數
            actual_window_w = int(MAIN_WINDOW_WIDTH * scaling)
            actual_window_h = int(MAIN_WINDOW_HEIGHT * scaling)

            # 置中計算
            center_x = (physical_w - actual_window_w) // 2
            center_y = (physical_h - actual_window_h) // 2 - 40

            self.geometry(
                f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}+{center_x}+{center_y}")

        except Exception:
            # 備用方案
            self.geometry(f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}+100+100")

    def _on_theme_change_from_settings(self, v: str):
        # 從設定子視窗切換主題：先切主題，再短暫奪回與釋放焦點避免卡死
        try:
            ctk.set_appearance_mode(v)
            # 同步保存至設定
            self.settings["theme"] = v
            self._save_settings()
        except Exception:
            return

    def _load_settings(self) -> dict:
        try:
            if SETTINGS_FILE.exists():
                # 載入並補齊預設鍵
                st = json.loads(SETTINGS_FILE.read_text("utf-8"))
                if "theme" not in st:
                    st["theme"] = "System"
                if "enable_system_notification" not in st:
                    st["enable_system_notification"] = True
                if "toast_x" not in st:
                    st["toast_x"] = ""
                if "toast_y" not in st:
                    st["toast_y"] = ""
                if "startup_enabled" not in st:
                    st["startup_enabled"] = is_startup_enabled()
                if "start_minimized_to_tray" not in st:
                    st["start_minimized_to_tray"] = False
                return st
        except Exception:
            pass
        return {
            "theme": "System",
            "enable_system_notification": True,
            "toast_x": "",
            "toast_y": "",
            "startup_enabled": is_startup_enabled(),
            "start_minimized_to_tray": False,
        }

    def _save_settings(self):
        try:
            SETTINGS_FILE.write_text(json.dumps(
                self.settings, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    # --- 設定視圖（全幅覆蓋主內容）---
    def open_settings_overlay(self):
        # 自動切換：關閉編輯頁面並清理記憶體
        self._cleanup_and_close_edit()
        self.close_settings_overlay()

        try:
            self.scroll.pack_forget()
        except Exception:
            pass

        container = ctk.CTkFrame(self.content)
        container.pack(fill="both", expand=True)
        self._settings_win = container

        # 標題列
        header = ctk.CTkFrame(container)
        header.pack(fill="x", padx=12, pady=(12, 0))
        ctk.CTkLabel(header, text="設定", font=self.font_large).pack(side="left")
        ctk.CTkButton(header, text="關閉", width=64, font=self.font_normal,
                      command=self.close_settings_overlay).pack(side="right")

        body = ctk.CTkFrame(container)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # 系統通知（純顯示）
        sys_ntf_var = tk.BooleanVar(value=bool(
            self.settings.get("enable_system_notification", True)))

        def _on_sys_ntf_toggle():
            self.settings["enable_system_notification"] = bool(
                sys_ntf_var.get())
            self._save_settings()
        ctk.CTkCheckBox(body, text="啟用系統通知（純顯示）", font=self.font_normal,
                        variable=sys_ntf_var, command=_on_sys_ntf_toggle).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # 應用通知位置
        ctk.CTkLabel(body, text="應用通知 X 座標", font=self.font_normal).grid(
            row=2, column=0, sticky="w")
        toast_x_var = tk.StringVar(value=str(self.settings.get("toast_x", "")))
        toast_x_entry = ctk.CTkEntry(
            body, textvariable=toast_x_var, width=120, font=self.font_normal)

        def _sanitize_x(*_):
            v = toast_x_var.get() or ""
            # 僅允許數字與負號，其餘移除，並限制最長6字（含負號）
            if not re.fullmatch(r"-?\d*", v):
                v = re.sub(r"[^0-9-]", "", v)
            if len(v) > 6:
                v = v[:6]
            if v != toast_x_var.get():
                toast_x_var.set(v)
        toast_x_var.trace_add("write", _sanitize_x)
        toast_x_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=6)

        ctk.CTkLabel(body, text="應用通知 Y 座標", font=self.font_normal).grid(
            row=3, column=0, sticky="w")
        toast_y_var = tk.StringVar(value=str(self.settings.get("toast_y", "")))
        toast_y_entry = ctk.CTkEntry(
            body, textvariable=toast_y_var, width=120, font=self.font_normal)

        def _sanitize_y(*_):
            v = toast_y_var.get() or ""
            # 僅允許數字與負號，其餘移除，並限制最長6字（含負號）
            if not re.fullmatch(r"-?\d*", v):
                v = re.sub(r"[^0-9-]", "", v)
            if len(v) > 6:
                v = v[:6]
            if v != toast_y_var.get():
                toast_y_var.set(v)
        toast_y_var.trace_add("write", _sanitize_y)
        toast_y_entry.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=6)

        def _save_toast_pos():
            x_txt = (toast_x_var.get() or "").strip()
            y_txt = (toast_y_var.get() or "").strip()

            def _ok(v: str) -> bool:
                return (v == "") or (re.fullmatch(r"-?\d{1,6}", v) is not None)
            if not _ok(x_txt) or not _ok(y_txt):
                messagebox.showwarning(
                    "座標輸入無效",
                )
                return
            self.settings["toast_x"] = x_txt
            self.settings["toast_y"] = y_txt
            self._save_settings()

        ctk.CTkButton(body, text="儲存位置", command=_save_toast_pos,
                      width=120, font=self.font_normal).grid(row=4, column=1, sticky="e")

        # 顏色模式
        ctk.CTkLabel(body, text="主題", font=self.font_normal).grid(
            row=5, column=0, sticky="w")
        theme_var = tk.StringVar(value=ctk.get_appearance_mode())
        theme_menu = ctk.CTkOptionMenu(
            body,
            values=["Light", "Dark", "System"],
            variable=theme_var,
            command=self._on_theme_change_from_settings,
            font=self.font_normal,
            dropdown_font=self.font_normal,
        )
        theme_menu.grid(row=5, column=1, sticky="w", padx=(8, 0), pady=6)

        # 開機自啟動
        ctk.CTkLabel(body, text="開機自啟動", font=self.font_normal).grid(
            row=6, column=0, sticky="w")
        startup_frame = ctk.CTkFrame(body)
        startup_frame.grid(row=6, column=1, sticky="w", padx=(8, 0), pady=6)

        self.enable_btn = ctk.CTkButton(startup_frame, text="啟用", width=80, font=self.font_normal,
                                        command=lambda: self._set_startup(True))
        self.enable_btn.pack(side="left", padx=(0, 4))

        self.disable_btn = ctk.CTkButton(startup_frame, text="停用", width=80, font=self.font_normal,
                                         command=lambda: self._set_startup(False))
        self.disable_btn.pack(side="left")

        self._update_startup_buttons()

        # 啟動時最小化至托盤
        start_min_var = tk.BooleanVar(value=bool(
            self.settings.get("start_minimized_to_tray", False)))

        def _on_toggle_start_min():
            self.settings["start_minimized_to_tray"] = bool(
                start_min_var.get())
            self._save_settings()

        ctk.CTkCheckBox(
            body,
            text="啟動時最小化至托盤",
            font=self.font_normal,
            variable=start_min_var,
            command=_on_toggle_start_min,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # --- 編輯視圖（全幅覆蓋主內容）---
    def open_edit_overlay(self, task_id: str, is_new: bool = False):
        # 自動切換：關閉設定頁面並清理記憶體
        self._cleanup_and_close_settings()
        self.close_edit_overlay()  # 關閉舊的編輯框

        self._edit_task_id = task_id
        self._is_new_task = is_new
        t = next((x for x in self.tasks if x.id == task_id), None)
        if not t:
            return

        # 隱藏列表，顯示全幅編輯容器
        try:
            self.scroll.pack_forget()
        except Exception:
            pass

        container = ctk.CTkFrame(self.content)
        container.pack(fill="both", expand=True)
        self._edit_win = container

        # 標題列（透明，移除深色背景條）
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 0))
        title_text = "新增任務" if is_new else f"編輯任務：{t.name}"
        ctk.CTkLabel(header, text=title_text,
                     font=self.font_large).pack(side="left")

        body = ctk.CTkFrame(container)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # 任務基本資訊（名稱、時間設定）
        form = ctk.CTkFrame(body)
        form.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(form, text="名稱", font=self.font_normal).grid(
            row=0, column=0, sticky="w")
        name_var = tk.StringVar(value=t.name)
        name_entry = ctk.CTkEntry(
            form, textvariable=name_var, width=140, font=self.font_normal)
        name_entry.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=6)

        # 限制名稱不超過8個字
        def _limit_name(*_):
            current = name_var.get()
            if len(current) > 8:
                name_var.set(current[:8])
        try:
            name_var.trace_add('write', _limit_name)
        except Exception:
            # 兼容較舊的 tkinter
            name_var.trace('w', _limit_name)

        # 時間輸入「數值 + 單位」
        ctk.CTkLabel(form, text="數值", font=self.font_normal).grid(
            row=1, column=0, sticky="w")
        val_var = tk.StringVar(value="")
        val_entry = ctk.CTkEntry(
            form, width=140, textvariable=val_var, font=self.font_normal)
        val_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=6)

        # 僅允許兩位數 1..99
        def _val_sanitizer(*_):
            s = val_var.get()
            ns = re.sub(r"\D+", "", s)[:2]
            if ns != s:
                val_var.set(ns)
        try:
            val_var.trace_add('write', _val_sanitizer)
        except Exception:
            pass

        unit_var2 = tk.StringVar(value="秒")
        unit_menu2 = ctk.CTkOptionMenu(
            form,
            values=[u for u, _ in TIME_UNITS],
            variable=unit_var2,
            width=80,
            font=self.font_normal,
            dropdown_font=self.font_normal,
        )
        unit_menu2.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=6)

        # 根據當前秒數自動選擇合適單位（讓值落在 1..99 內）
        try:
            secs_val = max(1, int(t.seconds))
        except Exception:
            secs_val = 1
        best_unit_name = "秒"
        best_value = secs_val
        for name, sec_per in reversed(TIME_UNITS):
            v = secs_val // sec_per
            if 1 <= v <= 99:
                best_unit_name = name
                best_value = v
                break
        unit_var2.set(best_unit_name)
        val_entry.delete(0, tk.END)
        val_entry.insert(0, str(best_value))

        # 說明（純文字渲染）
        desc_frame = ctk.CTkFrame(body)
        desc_frame.pack(fill="both", expand=True)

        # 說明標題列（透明，移除深色背景條）
        desc_header = ctk.CTkFrame(desc_frame, fg_color="transparent")
        desc_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(desc_header, text="說明", font=self.font_normal).pack(
            side="left", anchor="w")

        toggle_var = tk.BooleanVar(value=False)  # False=檢視, True=編輯

        editor = ctk.CTkTextbox(desc_frame, font=self.font_large)  # 編輯框也使用大字體
        editor.insert("1.0", t.description or "")

        # 使用標準 tk.Text 作為預覽
        is_dark_mode = ctk.get_appearance_mode() == "Dark"
        bg_color = "#212121" if is_dark_mode else "#ffffff"
        fg_color = "#ffffff" if is_dark_mode else "#000000"
        viewer = tk.Text(
            desc_frame,
            font=self.font_large,
            wrap="word",
            bg=bg_color,
            fg=fg_color,
            selectbackground="#0078d4",
            selectforeground="white",
            relief="flat",
            bd=0,
            cursor="arrow",
        )
        viewer.configure(state="disabled")

        def _render_preview():
            markdown_text = editor.get("1.0", "end-1c")
            viewer.configure(state="normal")
            viewer.delete("1.0", "end")
            viewer.configure(cursor="arrow")
            if not markdown_text:
                viewer.insert("1.0", "(無內容)")
            else:
                viewer.insert("1.0", markdown_text)
                url_pattern = r'https?://[^\s<>"]+'
                link_color = "#66B3FF" if is_dark_mode else "#0066CC"

                def _on_link_click(event):
                    index = viewer.index(f"@{event.x},{event.y}")
                    tags = viewer.tag_names(index)
                    if "link" in tags:
                        start_range = viewer.tag_prevrange(
                            "link", index + "+1c")
                        if start_range:
                            link_text = viewer.get(
                                start_range[0], start_range[1])
                            try:
                                webbrowser.open(link_text)
                            except Exception:
                                pass
                    return "break"

                def _on_link_enter(_):
                    viewer.configure(cursor="hand2")

                def _on_link_leave(_):
                    viewer.configure(cursor="arrow")

                def _on_text_motion(event):
                    try:
                        index = viewer.index(f"@{event.x},{event.y}")
                        tags = viewer.tag_names(index)
                        if "link" not in tags:
                            viewer.configure(cursor="arrow")
                    except Exception:
                        viewer.configure(cursor="arrow")

                viewer.bind("<Motion>", _on_text_motion)
                viewer.tag_configure(
                    "link", foreground=link_color, underline=True)
                viewer.tag_bind("link", "<Button-1>", _on_link_click)
                viewer.tag_bind("link", "<Enter>", _on_link_enter)
                viewer.tag_bind("link", "<Leave>", _on_link_leave)

                text_content = markdown_text
                for match in re.finditer(url_pattern, text_content):
                    start_pos = f"1.0+{match.start()}c"
                    end_pos = f"1.0+{match.end()}c"
                    viewer.tag_add("link", start_pos, end_pos)

            viewer.configure(state="disabled")

        def _toggle_edit():
            if toggle_var.get():
                toggle_var.set(False)
                t.description = editor.get("1.0", "end-1c")
                editor.pack_forget()
                viewer.pack(fill="both", expand=True, pady=(4, 8))
                _render_preview()
                toggle_btn.configure(text="編輯")
            else:
                toggle_var.set(True)
                viewer.pack_forget()
                editor.pack(fill="both", expand=True, pady=(4, 8))
                toggle_btn.configure(text="完成")

        toggle_btn = ctk.CTkButton(
            desc_header, text="編輯", width=64, font=self.font_normal, command=_toggle_edit)
        toggle_btn.pack(side="right")

        save_btn_text = "新增" if is_new else "儲存"
        ctk.CTkButton(
            header,
            text=save_btn_text,
            width=64,
            font=self.font_normal,
            command=lambda: self._save_task_inline_unit(
                t,
                name_var.get(),
                val_entry.get(),
                unit_var2.get(),
                is_new,
            ),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(header, text="返回", width=64, font=self.font_normal,
                      command=lambda: self._close_edit_overlay(is_new, t.id)).pack(side="right")

        viewer.pack(fill="both", expand=True, pady=(4, 8))
        _render_preview()

    def _save_task_inline_unit(self, t: Task, name: str, value_text: str, unit_name: str, is_new: bool = False):
        t.name = (name or "未命名").strip()[:8]  # 確保名稱不超過8字
        try:
            v = int(value_text)
        except Exception:
            v = 1
        v = max(1, min(99, v))
        unit = next((sec for n, sec in TIME_UNITS if n == unit_name), 1)
        sec = max(1, v * unit)
        t.seconds = sec
        t.due_at = int(time.time()) + sec
        t.remaining = sec
        t.notified = False
        save_tasks(self.tasks)

        # 儲存後自動回到任務列表
        self.close_edit_overlay()

        if is_new:
            self.refresh_rows(full=True)  # 新增時需要重新建立列表
        else:
            self.refresh_rows(full=False)

    def _cleanup_and_close_edit(self):
        """清理編輯視圖的記憶體並關閉"""
        if hasattr(self, '_edit_win') and self._edit_win is not None:
            try:
                self._edit_win.destroy()
            except Exception:
                pass
            self._edit_win = None

        # 清理相關變數
        if hasattr(self, '_edit_task_id'):
            self._edit_task_id = None
        if hasattr(self, '_is_new_task'):
            self._is_new_task = False

    def _cleanup_and_close_settings(self):
        """清理設定視圖的記憶體並關閉"""
        if hasattr(self, '_settings_win') and self._settings_win is not None:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
            self._settings_win = None

    def _close_edit_overlay(self, is_new: bool = False, task_id: str = None):
        # 如果是新增模式且取消，則刪除剛創建的任務
        if is_new and task_id:
            self.tasks = [t for t in self.tasks if t.id != task_id]
        self.close_edit_overlay()

    def close_edit_overlay(self):
        if self._edit_win is not None:
            try:
                self._edit_win.destroy()
            except Exception:
                pass
            self._edit_win = None
        self._edit_task_id = None
        self._is_new_task = False
        # 還原列表
        try:
            self.scroll.pack(fill="both", expand=True)
        except Exception:
            pass

    def close_settings_overlay(self):
        if self._settings_win is not None:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
            self._settings_win = None
        # 還原列表
        try:
            self.scroll.pack(fill="both", expand=True)
        except Exception:
            pass

    def refresh_rows(self, full: bool = False):
        if full:
            for child in list(self.scroll.children.values()):
                child.destroy()
            self.row_widgets.clear()
            for t in self.tasks:
                row = TaskRow(self.scroll, t, self.on_row_action)
                row.pack(fill="x", padx=4, pady=4)
                self.row_widgets[t.id] = row
        else:
            for t in self.tasks:
                if t.id in self.row_widgets:
                    self.row_widgets[t.id].refresh(t)

    def on_row_action(self, action: str, task_id: str):
        idx = next((i for i, t in enumerate(
            self.tasks) if t.id == task_id), -1)
        if idx < 0:
            return
        t = self.tasks[idx]

        if action == "start":
            # 若超過目標時間則不可開始
            if t.due_at and int(time.time()) >= int(t.due_at):
                pass
            else:
                t.is_running = True
                if not t.due_at:
                    t.due_at = int(time.time()) + t.seconds
                    t.notified = False

        elif action == "stop":
            t.is_running = False

        elif action == "reset":
            t.is_running = False
            t.due_at = int(time.time()) + t.seconds
            t.notified = False
        elif action == "delete":

            self.tasks.pop(idx)
            save_tasks(self.tasks)
            self.refresh_rows(full=True)
            return
        elif action == "edit":
            self.open_edit_overlay(task_id)
        save_tasks(self.tasks)
        self.refresh_rows(full=False)

    def on_add_task(self):
        # 自動切換：關閉設定頁面
        self._cleanup_and_close_settings()

        # 創建一個空任務用於新增
        new_task = Task(
            id=str(time.time_ns()),
            name="新任務",
            seconds=300,  # 預設5分鐘
            remaining=300,
            due_at=None,
            notified=False,
            description=""
        )
        self.tasks.append(new_task)
        self.open_edit_overlay(new_task.id, is_new=True)

    def _start_tick(self):
        self.after(1000, self._on_tick)

    def _on_tick(self):
        changed = False
        for t in self.tasks:
            if t.is_running and t.due_at:
                if int(time.time()) >= int(t.due_at) and not t.notified:
                    t.is_running = False
                    t.notified = True
                    # 一定顯示應用通知；系統通知視設定而定
                    self._show_in_app_toast(
                        "時間到", f"{t.name} 已到目標時間（點擊開啟編輯）", t.id)
                    if bool(self.settings.get("enable_system_notification", True)):
                        win_toast("時間到", f"{t.name} 已到目標時間")
                    changed = True
        # 若有任務在目標模式且正在跑，就刷新 UI
        any_running_goal = any(t.is_running and t.due_at for t in self.tasks)
        if changed:
            save_tasks(self.tasks)
            self.refresh_rows(full=False)
        elif any_running_goal:
            # 沒有資料寫入變更，但需要更新剩餘顯示
            self.refresh_rows(full=False)
        self._start_tick()

    # 開機自啟動控制
    def _update_startup_buttons(self):
        if not hasattr(self, "enable_btn") or not hasattr(self, "disable_btn"):
            return
        if is_startup_enabled():
            self.enable_btn.configure(state="disabled")
            self.disable_btn.configure(state="normal")
        else:
            self.enable_btn.configure(state="normal")
            self.disable_btn.configure(state="disabled")

    def _set_startup(self, enable: bool):
        try:
            if enable:
                create_startup_shortcut()
            else:
                remove_startup_shortcut()
            # 同步保存設定
            self.settings["startup_enabled"] = bool(enable)
            self._save_settings()
            self._update_startup_buttons()
        except Exception as e:
            messagebox.showwarning("失敗", f"設定開機啟動失敗：{e}")

    # 匯入/匯出
    def on_export(self):
        initial_dir = str(_app_base_dir())
        path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile="tasks-export.json",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="匯出任務到…",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps([asdict(t) for t in self.tasks],
                           ensure_ascii=False, indent=2),
                "utf-8",
            )
            messagebox.showinfo("匯出成功", f"已匯出到：{path}")
        except Exception as e:
            messagebox.showwarning("匯出失敗", str(e))

    def on_import(self):
        initial_dir = str(_app_base_dir())
        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="匯入任務…",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text("utf-8"))
            self.tasks = [Task.from_dict(x) for x in data]
            save_tasks(self.tasks)
            self.refresh_rows(full=True)
            messagebox.showinfo("匯入成功", f"已匯入：{path}")
        except Exception as e:
            messagebox.showwarning("匯入失敗", str(e))

    # --- 系統托盤整合 ---
    def _ensure_tray_libs(self) -> bool:
        if self._tray_ready:
            return True
        try:
            import pystray  # type: ignore
            from PIL import Image, ImageDraw  # type: ignore
            self._pystray = pystray
            self._PIL_Image = Image
            self._PIL_ImageDraw = ImageDraw
            self._tray_ready = True
            return True
        except Exception:
            self._tray_ready = False
            return False

    def _make_tray_image(self):
        # 產生一個簡單的 64x64 圓形圖示
        size = 64
        img = self._PIL_Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = self._PIL_ImageDraw.Draw(img)
        # 藍底白字 T 簡單圖樣
        draw.ellipse((0, 0, size - 1, size - 1), fill=(25, 118, 210, 255))
        # 畫一個白色的 T
        bar_w = size // 6
        # 橫槓
        draw.rectangle((size//6, size//5, size - size//6, size //
                       5 + bar_w), fill=(255, 255, 255, 255))
        # 直槓
        draw.rectangle((size//2 - bar_w//2, size//5, size//2 +
                       bar_w//2, size - size//6), fill=(255, 255, 255, 255))
        return img

    def _show_tray(self, minimize_if_missing: bool = True):
        if not self._ensure_tray_libs():
            if minimize_if_missing:
                # 缺少依賴時，退而求其次：最小化到工作列
                self.iconify()
            return
        if self._tray_icon is not None:
            return

        def _on_show(icon, item):
            self.after(0, self._restore_from_tray)

        def _on_exit(icon, item):
            self.after(0, self._exit_app)

        img = self._make_tray_image()
        menu = self._pystray.Menu(
            self._pystray.MenuItem("顯示主視窗", _on_show),
            self._pystray.MenuItem("結束", _on_exit)
        )
        self._tray_icon = self._pystray.Icon(APP_NAME, img, APP_NAME, menu)
        # 以背景執行，不阻塞 Tk 主迴圈
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _hide_tray(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.after(10, self.lift)
            self.after(20, lambda: self.focus_force())
        except Exception:
            pass

    def _exit_app(self):
        # 從托盤退出：先儲存設定，然後關閉托盤，再關閉主視窗
        self._save_settings()
        self._hide_tray()
        try:
            self.destroy()
        except Exception:
            os._exit(0)

    def on_close(self):
        # X 不結束程式，改縮到托盤
        try:
            # 關閉前記錄視窗位置大小
            try:
                self.update_idletasks()
                geo = self.geometry()
                size, _, pos = geo.partition("+")
                w_str, h_str = size.split("x")
                x_pos, y_pos = pos.split("+")
                self.settings["win_w"] = int(w_str)
                self.settings["win_h"] = int(h_str)
                self.settings["win_x"] = int(x_pos)
                self.settings["win_y"] = int(y_pos)
                # 註：不在關閉視窗時儲存設定，改為系統圖示結束時儲存
            except Exception:
                pass
            self.withdraw()
        except Exception:
            pass
        self._show_tray()
        # 可選：提醒一次

def load_tasks() -> list[Task]:
    if TASK_FILE.exists():
        try:
            data = json.loads(TASK_FILE.read_text("utf-8"))
            return [Task.from_dict(x) for x in data]
        except Exception:
            return []
    return []

def save_tasks(tasks: list[Task]):
    try:
        TASK_FILE.write_text(
            json.dumps([asdict(t) for t in tasks],
                       ensure_ascii=False, indent=2),
            "utf-8",
        )
    except Exception:
        pass

def _startup_dir() -> Path:
    return Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))

def get_startup_shortcut_path() -> Path:
    return _startup_dir() / "TaskTimer.lnk"

def is_startup_enabled() -> bool:
    return get_startup_shortcut_path().exists()

def create_startup_shortcut():
    from win32com.client import Dispatch  # type: ignore
    sd = _startup_dir()
    sd.mkdir(parents=True, exist_ok=True)
    # 在打包模式：target 指向 exe；直跑模式：target=python 解譯器，Arguments 指向腳本
    if getattr(sys, "frozen", False):
        target = sys.executable
        script = Path(sys.executable).resolve()
        workdir = script.parent
        args = ""
        icon_path = script
    else:
        target = sys.executable
        script = Path(__file__).resolve()
        workdir = script.parent
        args = f'"{script}"'
        icon_path = script
    shortcut_path = get_startup_shortcut_path()
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.Targetpath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = str(workdir)
    shortcut.IconLocation = str(icon_path)
    shortcut.save()

def remove_startup_shortcut():
    p = get_startup_shortcut_path()
    if p.exists():
        try:
            p.unlink()
        except PermissionError:
            # 可能被系統鎖定，嘗試設為可寫再刪除
            os.chmod(p, 0o666)
            p.unlink()

if __name__ == "__main__":
    # 支援從通知按下動作後直接開啟某任務的編輯覆蓋視窗
    target_task_id: str | None = None
    try:
        if "--edit-task" in sys.argv:
            i = sys.argv.index("--edit-task")
            if i + 1 < len(sys.argv):
                target_task_id = sys.argv[i + 1]
    except Exception:
        target_task_id = None

    app = App()
    if target_task_id:
        # 等待主視窗渲染後先喚起再開啟
        app.after(200, lambda: (app.show_and_focus(),
                  app.open_edit_overlay(target_task_id)))
    app.mainloop()
