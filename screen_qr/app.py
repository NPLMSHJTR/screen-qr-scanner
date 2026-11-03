# -*- coding: utf-8 -*-
"""
屏幕二维码识别工具（Windows 轻量桌面版）—— 实时投屏式预览 + 自动识别

像 scrcpy 那样，窗口里实时、连续地显示你的电脑屏幕画面（画面是"活"的），
同时对这个画面自动做二维码识别——登录二维码（QQ/微信/网页登录码）一出现，
就用原始全分辨率帧识别（不缩放，保留足够像素），识别到即弹出结果。

关键技术（针对"扫登录二维码"场景）：
  1. 识别用原始全分辨率帧（2560×1440 等），绝不缩小——登录码是密集 QR，
     缩到几十像素会丢失信息导致识别失败（已实测验证）
  2. 识别前做灰度 + 自适应二值化增强，提高低对比度/复杂码识别率
  3. 渲染显示时才等比缩放（仅给人看，不影响识别）
  4. 识别到弹出醒目结果框：显示完整内容 + 一键复制 + 打开链接

视觉：
  - 顶部标题条：左「屏幕扫码」+ 状态，右「暂停」「✕」
  - 中部：实时屏幕画面（缩放渲染）
  - 识别到二维码：画面中绿色框圈出
  - 底部：操作提示
  - 识别成功后：中央弹出结果卡片

交互：
  - 右键在画面拖矩形，只扫描该区域（R 键恢复全屏）
  - 空格暂停/恢复；双击复制；Esc 或 ✕ 退出
"""

import time
import threading
import webbrowser
import ctypes
import tkinter as tk

import cv2
import numpy as np
import mss
from PIL import Image, ImageTk

from .detector import QRDecoder


CORNER = "#07c160"
BAR_BG = "#222222"
BAR_FG = "#e8e8e8"
BAR_H = 40
FOOT_H = 34


def _enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class ScreenScanApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("屏幕扫码")
        self.root.configure(bg=BAR_BG)
        self.root.attributes("-topmost", True)

        self.W, self.H = 520, 380
        self.running = True
        self.scanning = True
        self._busy = False

        self.last_text = ""
        self.last_hit = 0.0
        self._last_capture = 0.0
        self._status = "实时预览中 · 二维码出现即自动识别"

        self.region = None          # None = 全屏
        self._sel_start = None
        self._sel_rect = None

        self._photo = None
        self._qbox = None           # 识别框（原始帧坐标）
        self._last_frame_size = (1, 1)

        self.decoder = QRDecoder()
        self._setup()
        self._bind()
        self._tick()

    # ---------------------------------------------------------------- UI
    def _setup(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 2}")
        self.root.minsize(360, 260)

        self.bar = tk.Frame(self.root, bg=BAR_BG, height=BAR_H)
        self.bar.pack(side="top", fill="x")
        self.bar.pack_propagate(False)

        tk.Label(self.bar, text="屏幕扫码", bg=BAR_BG, fg=BAR_FG,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left", padx=(14, 8), pady=8)

        self.status_lbl = tk.Label(self.bar, text=self._status, bg=BAR_BG, fg="#8a8a8a",
                                   font=("Microsoft YaHei UI", 9))
        self.status_lbl.pack(side="left", padx=2, pady=8)

        self.btn_pause = tk.Label(self.bar, text="暂停", bg=BAR_BG, fg=BAR_FG,
                                  font=("Microsoft YaHei UI", 10), width=5, cursor="hand2")
        self.btn_pause.pack(side="right", pady=8)
        self.btn_close = tk.Label(self.bar, text="✕", bg=BAR_BG, fg=BAR_FG,
                                  font=("Microsoft YaHei UI", 13), width=3, cursor="hand2")
        self.btn_close.pack(side="right", pady=6)
        self.btn_close.bind("<Button-1>", lambda e: self.close())
        self.btn_pause.bind("<Button-1>", lambda e: self._toggle_pause())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(bg="#e81123", fg="#ffffff"))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(bg=BAR_BG, fg=BAR_FG))

        self.canvas = tk.Canvas(self.root, bg="#000000", highlightthickness=0)
        self.canvas.pack(side="top", fill="both", expand=True)

        self.foot = tk.Frame(self.root, bg=BAR_BG, height=FOOT_H)
        self.foot.pack(side="bottom", fill="x")
        self.foot.pack_propagate(False)
        self.hint = tk.Label(self.foot,
                             text="右键拖框选区域 · 空格暂停 · 双击复制 · Esc 退出",
                             bg=BAR_BG, fg="#6a6a6a", font=("Microsoft YaHei UI", 9))
        self.hint.pack(expand=True)

    def _bind(self):
        c = self.canvas
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<ButtonPress-3>", self._sel_start_handler)
        c.bind("<B3-Motion>", self._sel_move_handler)
        c.bind("<ButtonRelease-3>", self._sel_end_handler)
        c.bind("<Double-Button-1>", lambda e: self._copy_last())

        self.root.bind("<Escape>", lambda e: self.close())
        self.root.bind("<space>", lambda e: self._toggle_pause())
        self.root.bind("<c>", lambda e: self._copy_last())
        self.root.bind("<r>", lambda e: self._reset_region())

    # ------------------------------------------------------ 框选区域
    def _sel_start_handler(self, e):
        self._sel_start = (e.x, e.y)
        self._sel_rect = (e.x, e.y, e.x, e.y)

    def _sel_move_handler(self, e):
        if self._sel_start:
            self._sel_rect = (self._sel_start[0], self._sel_start[1], e.x, e.y)

    def _sel_end_handler(self, e):
        if not self._sel_start:
            return
        x0, y0 = self._sel_start
        x1, y1 = e.x, e.y
        self._sel_start = None
        self._sel_rect = None
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        nx0, nx1 = sorted((min(x0, x1) / cw, max(x0, x1) / cw))
        ny0, ny1 = sorted((min(y0, y1) / ch, max(y0, y1) / ch))
        if nx1 - nx0 < 0.02 or ny1 - ny0 < 0.02:
            self.region = None
            self._status = "已恢复全屏扫描"
        else:
            self.region = (nx0, ny0, nx1, ny1)
            self._status = "已框选区域，仅扫描该区域"
        self.status_lbl.configure(text=self._status)

    def _reset_region(self):
        self.region = None
        self._status = "已恢复全屏扫描"
        self.status_lbl.configure(text=self._status)

    def _on_wheel(self, e):
        self._zoom(1.1 if e.delta > 0 else 0.9)

    def _zoom(self, factor):
        w = max(360, min(int(self.root.winfo_width() * factor), 2000))
        h = max(260, min(int(self.root.winfo_height() * factor), 2000))
        self.root.geometry(f"{w}x{h}")

    def _toggle_pause(self):
        self.scanning = not self.scanning
        self._status = "已暂停（空格恢复）" if not self.scanning else "实时预览中"
        self.status_lbl.configure(text=self._status)
        self.btn_pause.configure(text="继续" if not self.scanning else "暂停")

    # ------------------------------------------------------ 主循环
    def _tick(self):
        if not self.running:
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        now = time.time()
        if self.scanning and not self._busy and now - self._last_capture >= 0.2:
            self._last_capture = now
            self._capture_async()

        self.root.after(30, self._tick)

    def _capture_async(self):
        region = self._resolve_region()
        if region is None:
            return
        self._busy = True

        def worker():
            frame = None
            try:
                with mss.MSS() as sct:
                    shot = sct.grab(region)
                    frame = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
            except Exception:
                pass
            self.root.after(0, lambda: self._on_frame(frame))

        threading.Thread(target=worker, daemon=True).start()

    def _resolve_region(self):
        with mss.MSS() as sct:
            mon = sct.monitors[1]
        if self.region is None:
            return {"left": mon["left"], "top": mon["top"],
                    "width": mon["width"], "height": mon["height"]}
        nx0, ny0, nx1, ny1 = self.region
        left = mon["left"] + int(mon["width"] * nx0)
        top = mon["top"] + int(mon["height"] * ny0)
        w = int(mon["width"] * (nx1 - nx0))
        h = int(mon["height"] * (ny1 - ny0))
        if w < 2 or h < 2:
            return None
        return {"left": left, "top": top, "width": w, "height": h}

    def _on_frame(self, bgr):
        self._busy = False
        if bgr is None:
            return
        self._last_frame_size = (bgr.shape[1], bgr.shape[0])
        try:
            self._render(bgr)
        except Exception:
            pass

        if not self.scanning:
            return
        # 关键：用原始全分辨率帧识别（不缩小）
        text, pts = self.decoder.decode(bgr)
        if text:
            now = time.time()
            self._qbox = pts
            if text != self.last_text or now - self.last_hit > 2.0:
                self.last_text = text
                self.last_hit = now
                self._on_result(text)
        else:
            self._qbox = None

    # ------------------------------------------------------ 渲染
    def _render(self, bgr):
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        if cw <= 2 or ch <= 2:
            return

        h, w = bgr.shape[:2]
        scale = min(cw / w, ch / h)
        nw, nh = int(w * scale), int(h * scale)
        if nw < 1 or nh < 1:
            return
        resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))

        ox = (cw - nw) // 2
        oy = (ch - nh) // 2

        c = self.canvas
        c.delete("all")
        c.create_image(ox, oy, image=self._photo, anchor="nw")

        # 识别框（原始坐标 → 缩放后画布坐标）
        if self._qbox is not None:
            try:
                pts = np.array(self._qbox).reshape(-1, 2)
                flat = []
                for p in pts:
                    flat += [ox + p[0] * nw / w, oy + p[1] * nh / h]
                c.create_polygon(flat, outline=CORNER, width=3, fill="")
            except Exception:
                pass

        if self._sel_rect is not None:
            x0, y0, x1, y1 = self._sel_rect
            c.create_rectangle(x0, y0, x1, y1, outline="#ffcc00", width=1, dash=(4, 3))

    # ------------------------------------------------------ 结果
    def _on_result(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        opened = False
        if text.startswith(("http://", "https://")):
            try:
                webbrowser.open(text)
                opened = True
            except Exception:
                pass
        self._status = "已识别" + ("，已打开链接" if opened else "，已复制")
        self.status_lbl.configure(text=self._status)
        self._show_result_card(text, opened)

    def _show_result_card(self, text, opened):
        """弹出醒目结果卡片：完整内容 + 复制按钮 + 关闭。"""
        card = tk.Toplevel(self.root)
        card.title("识别结果")
        card.configure(bg="#1e1e1e")
        card.attributes("-topmost", True)
        cw = 460
        ch = 200
        x = self.root.winfo_x() + (self.root.winfo_width() - cw) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ch) // 2
        card.geometry(f"{cw}x{ch}+{max(0, x)}+{max(0, y)}")

        tk.Label(card, text="✓ 已识别到二维码", bg="#1e1e1e", fg=CORNER,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))

        box = tk.Frame(card, bg="#2a2a2a")
        box.pack(fill="both", expand=True, padx=16, pady=6)
        txt = tk.Text(box, bg="#2a2a2a", fg="#e8e8e8", wrap="word", relief="flat",
                      font=("Consolas", 10), height=5)
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        btnrow = tk.Frame(card, bg="#1e1e1e")
        btnrow.pack(fill="x", padx=16, pady=(4, 12))

        def do_copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            copy_btn.configure(text="已复制 ✓", fg=CORNER)

        copy_btn = tk.Label(btnrow, text="复制内容", bg="#3a3a3a", fg="#ffffff",
                            font=("Microsoft YaHei UI", 10), padx=18, pady=6, cursor="hand2")
        copy_btn.pack(side="left")
        copy_btn.bind("<Button-1>", lambda e: do_copy())

        close_btn = tk.Label(btnrow, text="关闭", bg="#3a3a3a", fg="#ffffff",
                             font=("Microsoft YaHei UI", 10), padx=18, pady=6, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: card.destroy())

    def _copy_last(self):
        if self.last_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_text)
            self._status = "已复制上次结果"
            self.status_lbl.configure(text=self._status)

    def run(self):
        self.root.mainloop()

    def close(self):
        self.running = False
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    _enable_dpi_awareness()
    ScreenScanApp().run()


if __name__ == "__main__":
    main()
