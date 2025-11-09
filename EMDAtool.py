# -*- coding: utf-8 -*-
"""
Created on Wed Oct 15 00:11:08 2025

@author: wadaso
"""

# -*- coding: utf-8 -*-
"""
Created on Wed Oct 15 00:05:17 2025

@author: wadaso
"""

# -*- coding: utf-8 -*-


import tkinter as tk
from tkinter import filedialog
from math import hypot
import json


class Line:
    def __init__(self, app, canvas, base_ratio, base_y_ratio, length, line_id):
        self.app = app
        self.canvas = canvas
        self.base_ratio = base_ratio
        self.base_y_ratio = base_y_ratio
        self.length = length
        self.line_id = line_id

        # 画面座標
        self.base_x = 0
        self.base_y = 0
        self.top_x = 0
        self.top_y = 0
        self.id = None

        # 上端の世界比率
        self.top_ratio_x = None
        self.top_ratio_y = None

        # スナップ
        self.parent = None
        self.children = []
        self.snap_t = None
        self.used_t_values = []

    # --- 世界↔画面 写像 ---
    def map_x(self, world_ratio_x, canvas_width):
        vmin, vmax = self.app.view_min, self.app.view_max
        w = max(1, canvas_width)
        return int(((world_ratio_x - vmin) / (vmax - vmin)) * w)

    def unmap_x(self, screen_x, canvas_width):
        vmin, vmax = self.app.view_min, self.app.view_max
        w = max(1, canvas_width)
        return (screen_x / w) * (vmax - vmin) + vmin

    # --- 幾何更新 ---
    def update_base_position(self, canvas_width, canvas_height):
        self.base_x = self.map_x(self.base_ratio, canvas_width)
        self.base_y = int(canvas_height * self.base_y_ratio)

        if self.parent is None and self.snap_t is None:
            if self.children and self.top_ratio_x is not None and self.top_ratio_y is not None:
                self.top_x = self.map_x(self.top_ratio_x, canvas_width)
                self.top_y = int(canvas_height * self.top_ratio_y)
            else:
                self.top_x = self.base_x
                self.top_y = self.base_y - self.length

    def update_top_ratios(self, canvas_width, canvas_height):
        if canvas_width > 0 and canvas_height > 0:
            self.top_ratio_x = self.unmap_x(self.top_x, canvas_width)
            self.top_ratio_y = self.top_y / canvas_height

    def draw(self):
        if self.id:
            self.canvas.delete(self.id)
        self.id = self.canvas.create_line(
            self.base_x, self.base_y, self.top_x, self.top_y, width=3, fill="black"
        )

    def move(self, dx, dy):
        self.top_x += dx
        self.top_y += dy
        self.update_top_ratios(self.canvas.winfo_width(), self.canvas.winfo_height())
        self.draw()
        for child in self.children:
            child.follow_parent()

    def follow_parent(self):
        if self.parent is None or self.snap_t is None:
            return
        x1, y1 = self.parent.base_x, self.parent.base_y
        x2, y2 = self.parent.top_x, self.parent.top_y
        t = self.snap_t
        self.top_x = x1 + t * (x2 - x1)
        self.top_y = y1 + t * (y2 - y1)
        self.update_top_ratios(self.canvas.winfo_width(), self.canvas.winfo_height())
        self.draw()
        for child in self.children:
            child.follow_parent()

    def get_top(self):
        return self.top_x, self.top_y

    def detach_from_parent(self):
        if self.parent:
            if self in self.parent.children:
                self.parent.children.remove(self)
            if self.snap_t in self.parent.used_t_values:
                self.parent.used_t_values.remove(self.snap_t)
        self.parent = None
        self.snap_t = None

    @staticmethod
    def generate_snap_t_values(count):
        return [(i + 1) / (count + 1) for i in range(count)]


class SnapHierarchyApp:
    def __init__(self, master, num_lines=6):
        self.master = master
        self.master.title("Snap Hierarchy App (％ズーム + パン対応・本数指定強化版)")
        self.length = 150
        self.base_y_ratio = 0.9
        self.margin = 0.05

        # viewport（世界 0.0〜1.0）
        self.view_min = 0.0
        self.view_max = 1.0
        self._min_span = 0.02   # 2% 以下にはしない（極端ズーム抑制）
        self._pan_margin = 0.0005

        # 状態
        self.add_mode = False
        self.delete_mode = False
        self.split_mode = False

        self.guide_circles = []
        self.delete_guides = []
        self.snap_candidates = []
        self.lines = []

        # 上段テキスト
        self.text_entries = []

        # 下段（グループ行）
        self.group_row_frame = None
        self.group_canvas = None
        self.group_entries = []
        self.group_boundaries = []
        self.group_text_cache = []
        self.group_separators = []

        self.top_entry_window_ids = []
        self.group_window_id = None

        self.drag_target = None
        self.start_xy = (0, 0)

        # パン（中/右ドラッグ）
        self.panning = False
        self.pan_last_x = None

        self.setup_ui(num_lines)
        self.bind_events()
        self.add_menu_bar()

        self.undo_stack = []
        self.redo_stack = []

    # ---------- UI ----------
    def setup_ui(self, num_lines):
        control_frame = tk.Frame(self.master)
        control_frame.pack(fill="x")

        # 左：モード
        mode_frame = tk.Frame(control_frame)
        mode_frame.pack(side=tk.LEFT, padx=10)

        self.add_button = tk.Button(mode_frame, text="＋ 追加モード OFF", command=self.toggle_add_mode)
        self.add_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = tk.Button(mode_frame, text="− 削除モード OFF", command=self.toggle_delete_mode)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.split_button = tk.Button(mode_frame, text="｜ 分割モード OFF", command=self.toggle_split_mode)
        self.split_button.pack(side=tk.LEFT, padx=5)

        # 中央：表示範囲
        zoom_frame = tk.Frame(control_frame)
        zoom_frame.pack(side=tk.LEFT, padx=20)

        tk.Label(zoom_frame, text="表示範囲(％)：").pack(side=tk.LEFT)
        self.view_min_var = tk.StringVar(value="0")
        self.view_max_var = tk.StringVar(value="100")
        self.view_min_entry = tk.Entry(zoom_frame, textvariable=self.view_min_var, width=5, justify="right")
        self.view_max_entry = tk.Entry(zoom_frame, textvariable=self.view_max_var, width=5, justify="right")
        self.view_min_entry.pack(side=tk.LEFT)
        tk.Label(zoom_frame, text="〜").pack(side=tk.LEFT)
        self.view_max_entry.pack(side=tk.LEFT)
        tk.Button(zoom_frame, text="適用", command=self.apply_view_range, bg="#efe").pack(side=tk.LEFT, padx=6)

        # 右：アクション/UndoRedo/本数
        action_frame = tk.Frame(control_frame)
        action_frame.pack(side=tk.RIGHT, padx=10)
        tk.Button(action_frame, text="＋線を追加", command=self.append_line,
                  bg="#f88", activebackground="#faa").pack(side=tk.LEFT, padx=5)
        tk.Button(action_frame, text="−線を削除", command=self.remove_last_line,
                  bg="#88f", activebackground="#aaf").pack(side=tk.LEFT, padx=5)

        # 本数エリア
        entry_frame = tk.Frame(control_frame)
        entry_frame.pack(side=tk.RIGHT, padx=10)
        tk.Label(entry_frame, text="線の本数:").pack(side=tk.LEFT)

        # 数字バリデーション
        vcmd = (self.master.register(self._validate_int), "%P")
        self.line_count_var = tk.StringVar(value=str(num_lines))
        self.line_count_entry = tk.Entry(entry_frame, textvariable=self.line_count_var, width=6,
                                         validate="key", validatecommand=vcmd, justify="right")
        self.line_count_entry.pack(side=tk.LEFT)

        # 適用ボタン
        tk.Button(entry_frame, text="適用", command=self.apply_line_count, bg="#ffe").pack(side=tk.LEFT, padx=4)

        # エントリの操作バインド
        self.line_count_entry.bind("<Return>", self.update_line_count_from_entry)
        self.line_count_entry.bind("<FocusOut>", self.update_line_count_from_entry)
        self.line_count_entry.bind("<Up>", lambda e: self._step_line_count(+1))
        self.line_count_entry.bind("<Down>", lambda e: self._step_line_count(-1))

        # キャンバス
        self.canvas = tk.Canvas(self.master, bg="white")
        self.canvas.pack(fill="both", expand=True)

        self.create_lines(num_lines)
        self._update_status()

    def _validate_int(self, P: str) -> bool:
        """エントリの入力が空 or 正の整数なら許可"""
        return (P == "") or (P.isdigit() and int(P) >= 1)

    def _step_line_count(self, step: int):
        cur = int(self.line_count_var.get() or "0")
        new_val = max(1, cur + step)
        self.line_count_var.set(str(new_val))
        self.apply_line_count()

    def apply_line_count(self):
        self.update_line_count_from_entry()

    def _update_status(self):
        pass
    # ---------- ビューポート操作 ----------
    def apply_view_range(self):
        try:
            vmin = float(self.view_min_var.get()) / 100.0
            vmax = float(self.view_max_var.get()) / 100.0
        except ValueError:
            return
        if not (0.0 <= vmin < vmax <= 1.0):
            return
        if (vmax - vmin) < self._min_span:
            center = (vmin + vmax) / 2
            vmin = max(0.0, center - self._min_span / 2)
            vmax = min(1.0, center + self._min_span / 2)
        self.view_min, self.view_max = vmin, vmax
        self.view_min_var.set(str(int(round(vmin * 100))))
        self.view_max_var.set(str(int(round(vmax * 100))))
        self.redraw_all()
        self._update_status()

    def _clamp_view(self, vmin, vmax):
        span = max(self._min_span, min(1.0, vmax - vmin))
        center = (vmin + vmax) / 2
        vmin = max(0.0 + 1e-9, center - span / 2)
        vmax = min(1.0 - 1e-9, center + span / 2)
        if vmin < 0.0:
            vmax -= vmin
            vmin = 0.0
        if vmax > 1.0:
            vmin -= (vmax - 1.0)
            vmax = 1.0
        return vmin, vmax

    def zoom_at_worldx(self, world_x, factor):
        vmin, vmax = self.view_min, self.view_max
        span = (vmax - vmin) / factor
        span = max(self._min_span, min(1.0, span))
        left_ratio = (world_x - vmin) / (vmax - vmin) if vmax > vmin else 0.5
        new_vmin = world_x - span * left_ratio
        new_vmax = new_vmin + span
        new_vmin, new_vmax = self._clamp_view(new_vmin, new_vmax)
        self.view_min, self.view_max = new_vmin, new_vmax
        self.view_min_var.set(str(int(round(new_vmin * 100))))
        self.view_max_var.set(str(int(round(new_vmax * 100))))
        self.redraw_all()
        self._update_status()

    def pan_by(self, dx_world):
        vmin = self.view_min + dx_world
        vmax = self.view_max + dx_world
        vmin, vmax = self._clamp_view(vmin, vmax)
        self.view_min, self.view_max = vmin, vmax
        self.view_min_var.set(str(int(round(vmin * 100))))
        self.view_max_var.set(str(int(round(vmax * 100))))
        self.redraw_all()
        self._update_status()

    # ---------- モード切替 ----------
    def toggle_add_mode(self):
        self.add_mode = not self.add_mode
        if self.add_mode:
            self.delete_mode = False
            self.add_button.config(text="◉ 追加モード ON", bg="#fdd", fg="darkred", activebackground="#fcc")
            self.delete_button.config(text="− 削除モード OFF", bg="SystemButtonFace", fg="black")
            self.show_insert_guides()
            self.clear_delete_guides()
        else:
            self.add_button.config(text="＋ 追加モード OFF", bg="SystemButtonFace", fg="black")
            self.clear_insert_guides()
        self.canvas.config(bg="#eef" if self.add_mode else ("#ddd" if self.delete_mode else "white"))

    def toggle_delete_mode(self):
        self.delete_mode = not self.delete_mode
        if self.delete_mode:
            self.add_mode = False
            self.delete_button.config(text="◉ 削除モード ON", bg="#ddf", fg="darkblue", activebackground="#ccf")
            self.add_button.config(text="＋ 追加モード OFF", bg="SystemButtonFace", fg="black")
            self.clear_insert_guides()
            self.show_delete_guides()
        else:
            self.delete_button.config(text="− 削除モード OFF", bg="SystemButtonFace", fg="black")
            self.clear_delete_guides()
        self.canvas.config(bg="#ddd" if self.delete_mode else ("#eef" if self.add_mode else "white"))

    def toggle_split_mode(self):
        self.split_mode = not self.split_mode
        if self.split_mode:
            self.split_button.config(text="｜ 分割モード ON", bg="#efe", fg="darkgreen", activebackground="#dfd")
        else:
            self.split_button.config(text="｜ 分割モード OFF", bg="SystemButtonFace", fg="black")
        if self.group_row_frame is not None:
            self.group_row_frame.configure(bg="#eef" if self.split_mode else "#fafafa")
            if self.group_canvas is not None:
                self.group_canvas.configure(bg="#eef" if self.split_mode else "#fafafa")

    # ---------- バインド ----------
    def bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # 中ボタン/右ボタンでパン
        for btn in (2, 3):
            self.canvas.bind(f"<ButtonPress-{btn}>", self.on_pan_start)
            self.canvas.bind(f"<B{btn}-Motion>", self.on_pan_drag)
            self.canvas.bind(f"<ButtonRelease-{btn}>", self.on_pan_end)

        # ホイール（Windows/macOS）
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        # Linux（X11）
        self.canvas.bind("<Button-4>", lambda e: self.on_wheel_linux(+1, e))
        self.canvas.bind("<Button-5>", lambda e: self.on_wheel_linux(-1, e))

        self.canvas.bind("<Configure>", self.on_resize)

        # キー
        self.master.bind_all("<Control-z>", lambda event: self.undo())
        self.master.bind_all("<Control-y>", lambda event: self.redo())
        self.master.bind_all("+", lambda e: self.zoom_keyboard(1.2))
        self.master.bind_all("-", lambda e: self.zoom_keyboard(1/1.2))
        self.master.bind_all("<Left>", lambda e: self.pan_keyboard(-0.05))
        self.master.bind_all("<Right>", lambda e: self.pan_keyboard(+0.05))
        self.master.bind_all("0", lambda e: self.reset_view())

    # ---------- ホイール/パン ----------
    def canvas_x_to_world(self, x_screen):
        w = max(1, self.canvas.winfo_width())
        return (x_screen / w) * (self.view_max - self.view_min) + self.view_min

    def on_wheel(self, event):
        if (event.state & 0x0001) != 0:  # Shift
            steps = (event.delta / 120) if event.delta else 0
            dx_world = -steps * (self.view_max - self.view_min) * 0.05
            self.pan_by(dx_world)
            return
        world_x = self.canvas_x_to_world(event.x)
        factor = 1.2 if (event.delta > 0) else (1/1.2)
        self.zoom_at_worldx(world_x, factor)

    def on_wheel_linux(self, direction, event):
        if (event.state & 0x0001) != 0:  # Shift
            dx_world = -direction * (self.view_max - self.view_min) * 0.05
            self.pan_by(dx_world)
            return
        world_x = self.canvas_x_to_world(event.x)
        factor = 1.2 if (direction > 0) else (1/1.2)
        self.zoom_at_worldx(world_x, factor)

    def on_pan_start(self, event):
        self.panning = True
        self.pan_last_x = event.x

    def on_pan_drag(self, event):
        if not self.panning:
            return
        dx_px = event.x - self.pan_last_x
        self.pan_last_x = event.x
        w = max(1, self.canvas.winfo_width())
        dx_world = -(dx_px / w) * (self.view_max - self.view_min)
        if abs(dx_world) < self._pan_margin:
            return
        self.pan_by(dx_world)

    def on_pan_end(self, event):
        self.panning = False
        self.pan_last_x = None

    def zoom_keyboard(self, factor):
        world_x = (self.view_min + self.view_max) / 2
        self.zoom_at_worldx(world_x, factor)

    def pan_keyboard(self, fraction):
        self.pan_by((self.view_max - self.view_min) * fraction)

    def reset_view(self):
        self.view_min, self.view_max = 0.0, 1.0
        self.view_min_var.set("0")
        self.view_max_var.set("100")
        self.redraw_all()
        self._update_status()

    # ---------- 線 本数変更など ----------
    def update_line_count_from_entry(self, event=None):
        try:
            if not self.line_count_var.get():
                return
            new_count = int(self.line_count_var.get())
            if new_count < 1:
                return
            current_count = len(self.lines)
            if new_count == current_count:
                return

            self._snapshot_group_texts()

            if new_count > current_count:
                for _ in range(new_count - current_count):
                    new_id = max((line.line_id for line in self.lines), default=0) + 1
                    self.lines.append(Line(self, self.canvas, 0.5, self.base_y_ratio, self.length, new_id))
            else:
                for _ in range(current_count - new_count):
                    line = self.lines.pop()
                    line.detach_from_parent()
                    for child in list(line.children):
                        child.detach_from_parent()
                    self.canvas.delete(line.id)

            # グループ境界を現在の本数に合わせてクランプ
            self.group_boundaries = [b for b in self.group_boundaries if 1 <= b <= max(0, new_count - 2)]

            self.renormalize_ratios()
            self.redraw_all()

            # UI と実際の本数の同期
            self.line_count_var.set(str(len(self.lines)))
        except ValueError:
            pass

    def create_lines(self, num):
        self.lines.clear()
        for i in range(num):
            ratio = self.margin + (1 - 2 * self.margin) * (i / (num - 1)) if num > 1 else 0.5
            self.lines.append(Line(self, self.canvas, ratio, self.base_y_ratio, self.length, i))
        self.redraw_all()

    def redraw_all(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        for line in self.lines:
            line.update_base_position(width, height)
            line.draw()
        for line in self.lines:
            if line.parent:
                line.follow_parent()
        if self.add_mode:
            self.show_insert_guides()
        if self.delete_mode:
            self.show_delete_guides()
        self.draw_text_rows_and_group_row()

    # ---------- 上段/下段 UI ----------
    def _snapshot_current_texts(self):
        self._top_text_map = {}
        for frame in self.text_entries:
            entry = frame.winfo_children()[0]
            key = getattr(frame, "left_line_id", None)
            if key is not None:
                self._top_text_map[key] = entry.get()
        self.group_text_cache = [e.get() for e in self.group_entries] if self.group_entries else list(self.group_text_cache)

    def _snapshot_group_texts(self):
        if self.group_entries:
            self.group_text_cache = [e.get() for e in self.group_entries]

    def draw_text_rows_and_group_row(self):
        self._snapshot_current_texts()

        for wid in getattr(self, "top_entry_window_ids", []):
            self.canvas.delete(wid)
        self.top_entry_window_ids.clear()
        if getattr(self, "group_window_id", None):
            self.canvas.delete(self.group_window_id)
            self.group_window_id = None

        for frame in self.text_entries:
            frame.destroy()
        self.text_entries.clear()

        if self.group_row_frame is not None:
            for sep in self.group_separators:
                sep.destroy()
            self.group_separators.clear()
            self.group_row_frame.destroy()
            self.group_row_frame = None
            self.group_canvas = None
            self.group_entries.clear()

        if len(self.lines) < 2:
            return

        entry_height = 24
        gap = 2
        group_row_height = 32

        xs = [ln.base_x for ln in self.lines]
        ys = [ln.base_y for ln in self.lines]
        left_x, right_x = xs[0], xs[-1]
        top_y = min(ys)

        # 上段
        for i in range(len(self.lines) - 1):
            line1, line2 = self.lines[i], self.lines[i + 1]
            x1 = line1.base_x
            x2 = line2.base_x
            width_px = abs(x2 - x1)

            frame = tk.Frame(
                self.canvas, width=width_px, height=24,
                bd=0, relief="flat",
                highlightthickness=1, highlightbackground="#000", bg="white"
            )
            frame.pack_propagate(False)
            entry = tk.Entry(frame, bd=0, relief="flat", font=("Meiryo", 13),
                             justify="center", highlightthickness=0)
            entry.pack(fill="both", expand=True)

            if hasattr(self, "_top_text_map") and line1.line_id in self._top_text_map:
                entry.insert(0, self._top_text_map[line1.line_id])

            w_id = self.canvas.create_window(x1, top_y, window=frame, anchor="nw")
            self.top_entry_window_ids.append(w_id)
            frame.left_line_id = line1.line_id
            self.text_entries.append(frame)

        # 下段：行
        total_w = right_x - left_x
        self.group_row_frame = tk.Frame(
            self.canvas, width=total_w, height=group_row_height,
            bd=0, relief="flat", highlightthickness=1, highlightbackground="#000",
            bg=("#eef" if self.split_mode else "#fafafa")
        )
        self.group_row_frame.pack_propagate(False)
        self.canvas.create_window(left_x, top_y + entry_height + gap, window=self.group_row_frame, anchor="nw")

        self.group_canvas = tk.Canvas(
            self.group_row_frame, height=group_row_height, highlightthickness=0,
            bg=("#eef" if self.split_mode else "#fafafa")
        )
        self.group_canvas.pack(fill="both", expand=True)

        max_idx = max(0, len(self.lines) - 2)
        self.group_boundaries = sorted([b for b in self.group_boundaries if 1 <= b <= max_idx])

        self.group_canvas.bind("<Button-1>", lambda e: self._handle_split_click_local(e.x))
        self._rebuild_group_row()
        self.master.after_idle(self._rebuild_group_row)

    def _handle_split_click_local(self, x_local):
        if not self.split_mode or len(self.lines) < 3:
            return

        self._snapshot_group_texts()
        xs = [ln.base_x for ln in self.lines]
        left_x = xs[0]
        cand, cand_dist = None, 1e9
        for j in range(1, len(self.lines) - 1):
            x_rel = xs[j] - left_x
            d = abs(x_rel - x_local)
            if d < cand_dist:
                cand_dist, cand = d, j
        if cand is None or cand_dist > 10:
            return

        self.push_undo_state()
        if cand in self.group_boundaries:
            self.group_boundaries = [b for b in self.group_boundaries if b != cand]
        else:
            self.group_boundaries = sorted(set(self.group_boundaries + [cand]))
        self._rebuild_group_row()
        self.master.after_idle(self._rebuild_group_row)

    def _clear_group_overlays(self):
        for sep in self.group_separators:
            sep.destroy()
        self.group_separators.clear()

    def _rebuild_group_row(self):
        if self.group_row_frame is None or len(self.lines) < 2:
            return

        xs = [ln.base_x for ln in self.lines]
        left_x = xs[0]
        h = self.group_row_frame.winfo_height() or 32
        pad = 3

        self.group_canvas.delete("all")
        for j in range(len(self.lines)):
            x_rel = xs[j] - left_x
            self.group_canvas.create_line(x_rel, 0, x_rel, h, fill="#e2e2e2")

        self._clear_group_overlays()
        for e in self.group_entries:
            e.destroy()
        self.group_entries.clear()

        starts = [0] + sorted([b for b in self.group_boundaries if 1 <= b <= len(self.lines) - 2]) + [len(self.lines) - 1]
        old = list(self.group_text_cache or [])
        oi = 0

        for a, b in zip(starts[:-1], starts[1:]):
            seg_left = xs[a] - left_x
            seg_right = xs[b] - left_x
            seg_w = max(1, seg_right - seg_left)

            entry = tk.Entry(
                self.group_row_frame,
                bd=0, relief="flat",
                highlightthickness=1, highlightbackground="#000",
                font=("Meiryo", 12), justify="center"
            )
            entry.place(x=seg_left + pad, y=3, width=seg_w - pad * 2, height=h - 6)
            entry.bind(
                "<Button-1>",
                lambda e, self=self: self._handle_split_click_local(
                    e.x_root - self.group_row_frame.winfo_rootx()
                )
            )

            if oi < len(old):
                entry.insert(0, old[oi])
            oi += 1

            entry.lift()
            self.group_entries.append(entry)

        for b in self.group_boundaries:
            x_rel = xs[b] - left_x
            sep = tk.Frame(self.group_row_frame, bg="#000")
            sep.place(x=x_rel - 1, y=0, width=2, height=h)
            sep.bind("<Button-1>", lambda e, x=x_rel: self._handle_split_click_local(x))
            sep.lift()
            self.group_separators.append(sep)

        self.group_text_cache = [e.get() for e in self.group_entries]

    # ---------- リサイズ ----------
    def on_resize(self, event):
        self._snapshot_group_texts()
        self.redraw_all()
        self.master.after_idle(self._rebuild_group_row)

    # ---------- ガイド ----------
    def show_insert_guides(self):
        self.clear_insert_guides()
        r = 6
        for i, line in enumerate(self.lines):
            cx, cy = line.top_x, line.top_y
            oid = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="red")
            self.guide_circles.append((oid, i, cx, cy))

    def clear_insert_guides(self):
        for oid, *_ in self.guide_circles:
            self.canvas.delete(oid)
        self.guide_circles.clear()

    def show_delete_guides(self):
        self.clear_delete_guides()
        r = 6
        for line in self.lines:
            tx, ty = line.get_top()
            oid = self.canvas.create_oval(tx - r, ty - r, tx + r, ty + r, fill="blue")
            self.delete_guides.append(oid)

    def clear_delete_guides(self):
        for oid in self.delete_guides:
            self.canvas.delete(oid)
        self.delete_guides.clear()

    def show_snap_candidates(self, dragged_line):
        self.clear_snap_candidates()
        def get_descendants(line):
            res, st = set(), [line]
            while st:
                cur = st.pop()
                for ch in cur.children:
                    if ch not in res:
                        res.add(ch); st.append(ch)
            return res
        # 必要なら候補描画を実装

    def clear_snap_candidates(self):
        for oid in self.snap_candidates:
            self.canvas.delete(oid)
        self.snap_candidates.clear()

    # ---------- 追加/削除 ----------
    def insert_line_at_index(self, index):
        self._snapshot_group_texts()
        self.push_undo_state()
        new_id = max((line.line_id for line in self.lines), default=0) + 1
        self.lines.insert(index, Line(self, self.canvas, 0.5, self.base_y_ratio, self.length, new_id))
        self.renormalize_ratios()
        self.redraw_all()
        self.line_count_var.set(str(len(self.lines)))

    def append_line(self):
        self.insert_line_at_index(len(self.lines))

    def remove_last_line(self):
        if len(self.lines) <= 1:
            return
        self._snapshot_group_texts()
        self.push_undo_state()
        line = self.lines.pop()
        line.detach_from_parent()
        for child in list(line.children):
            child.detach_from_parent()
        self.canvas.delete(line.id)
        self.renormalize_ratios()
        self.group_boundaries = [b for b in self.group_boundaries if 1 <= b <= len(self.lines) - 2]
        self.redraw_all()
        self.line_count_var.set(str(len(self.lines)))

    def renormalize_ratios(self):
        n = len(self.lines)
        for i, line in enumerate(self.lines):
            line.base_ratio = self.margin + (1 - 2 * self.margin) * (i / (n - 1)) if n > 1 else 0.5

    # ---------- マウス（上端ドラッグ系） ----------
    def on_press(self, event):
        self.start_xy = (event.x, event.y)
        if self.add_mode:
            for (_, index, cx, cy) in self.guide_circles:
                if hypot(event.x - cx, event.y - cy) < 10:
                    self.insert_line_at_index(index); return
            return
        if self.delete_mode:
            for line in self.lines:
                tx, ty = line.get_top()
                if self.distance(event.x, event.y, tx, ty) < 15:
                    self._snapshot_group_texts()
                    self.push_undo_state()
                    line.detach_from_parent()
                    for child in list(line.children):
                        child.detach_from_parent()
                    self.canvas.delete(line.id)
                    self.lines.remove(line)
                    self.renormalize_ratios()
                    self.group_boundaries = [b for b in self.group_boundaries if 1 <= b <= len(self.lines) - 2]
                    self.redraw_all()
                    self.line_count_var.set(str(len(self.lines)))
                    return
            return
        for line in self.lines:
            tx, ty = line.get_top()
            if self.distance(event.x, event.y, tx, ty) < 15:
                self.drag_target = line; break
        if self.drag_target:
            self.show_snap_candidates(self.drag_target)

    def on_drag(self, event):
        if not self.drag_target:
            return
        dx = event.x - self.start_xy[0]
        dy = event.y - self.start_xy[1]
        self.start_xy = (event.x, event.y)
        self.drag_target.move(dx, dy)

    def on_release(self, event):
        if not self.drag_target:
            return
        snapped = False
        for other in self.lines:
            if other == self.drag_target:
                continue
            if self.is_near(self.drag_target, other):
                # 循環検出は残す（条件④のみ削除リクエストのため）
                if self.detect_cycle(self.drag_target, other):
                    continue
                self.drag_target.detach_from_parent()
                tx, ty = self.drag_target.get_top()
                closest_t, min_dist = None, float("inf")
                for t in Line.generate_snap_t_values(len(self.lines) - 1):
                    if t in other.used_t_values:
                        continue
                    x1 = other.base_x + t * (other.top_x - other.base_x)
                    y1 = other.base_y + t * (other.top_y - other.base_y)
                    d = hypot(x1 - tx, y1 - ty)
                    if d < min_dist:
                        min_dist, closest_t = d, t
                if closest_t is not None:
                    # --- 交差チェックを削除し、即スナップ確定 ---
                    snap_x = other.base_x + closest_t * (other.top_x - other.base_x)
                    snap_y = other.base_y + closest_t * (other.top_y - other.base_y)
                    self.push_undo_state()
                    other.used_t_values.append(closest_t)
                    self.drag_target.snap_t = closest_t
                    self.drag_target.parent = other
                    other.children.append(self.drag_target)
                    # 上端をスナップ位置に合わせた上で追従
                    self.drag_target.top_x = snap_x
                    self.drag_target.top_y = snap_y
                    self.drag_target.follow_parent()
                    snapped = True
                    break
        if not snapped:
            self.drag_target.detach_from_parent()
        self.drag_target = None
        self.clear_snap_candidates()

    # ---------- 幾何 ----------
    def is_near(self, line1, line2):
        x1, y1 = line1.get_top()
        x2, y2 = line2.base_x, line2.base_y
        x3, y3 = line2.top_x, line2.top_y
        return self.point_to_segment_distance((x2, y2), (x3, y3), (x1, y1)) < 25

    def point_to_segment_distance(self, A, B, P):
        (x1, y1), (x2, y2), (x3, y3) = A, B, P
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            return hypot(x3 - x1, y3 - y1)
        t = max(0, min(1, ((x3 - x1) * dx + (y3 - y1) * dy) / (dx * dx + dy * dy)))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return hypot(x3 - proj_x, y3 - proj_y)

    def detect_cycle(self, child, new_parent):
        cur = new_parent
        while cur:
            if cur == child:
                return True
            cur = cur.parent
        return False

    def distance(self, x1, y1, x2, y2):
        return hypot(x1 - x2, y1 - y2)

    # ---------- メニュー ----------
    def add_menu_bar(self):
        menubar = tk.Menu(self.master)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="保存", command=self.save_state)
        filemenu.add_command(label="読み込み", command=self.load_state)
        menubar.add_cascade(label="ファイル", menu=filemenu)
        editmenu = tk.Menu(menubar, tearoff=0)
        editmenu.add_command(label="Undo", command=self.undo)
        editmenu.add_command(label="Redo", command=self.redo)
        viewmenu = tk.Menu(menubar, tearoff=0)
        viewmenu.add_command(label="リセット (0〜100%)", command=self.reset_view)
        menubar.add_cascade(label="表示", menu=viewmenu)
        self.master.config(menu=menubar)

    # ---------- Undo/Redo & Save/Load ----------
    def push_undo_state(self):
        self._snapshot_group_texts()
        state = self.capture_state()
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def capture_state(self):
        lines_data = []
        for line in self.lines:
            lines_data.append({
                "id": line.line_id,
                "base_ratio": line.base_ratio,
                "top_ratio_x": line.top_ratio_x,
                "top_ratio_y": line.top_ratio_y,
                "parent_id": line.parent.line_id if line.parent else None,
                "snap_t": line.snap_t
            })
        top_texts = {}
        for frame in self.text_entries:
            entry = frame.winfo_children()[0]
            key = getattr(frame, "left_line_id", None)
            if key is not None:
                top_texts[str(key)] = entry.get()
        group = {
            "boundaries": list(self.group_boundaries),
            "texts": [e.get() for e in self.group_entries] if self.group_entries else list(self.group_text_cache)
        }
        return {"lines": lines_data, "top_texts": top_texts, "group": group,
                "view": {"min": self.view_min, "max": self.view_max}}

    def restore_state(self, state):
        self.lines.clear()
        self.canvas.delete("all")

        line_dict = {}
        for item in state["lines"]:
            line = Line(self, self.canvas, item["base_ratio"], self.base_y_ratio, self.length, item["id"])
            line.top_ratio_x = item.get("top_ratio_x", 0.5)
            line.top_ratio_y = item.get("top_ratio_y", 0.5)
            line_dict[item["id"]] = line
            self.lines.append(line)

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        for line in self.lines:
            line.update_base_position(width, height)
            if line.top_ratio_x is None or line.top_ratio_y is None:
                line.top_x = line.base_x
                line.top_y = line.base_y - self.length
            else:
                line.top_x = line.map_x(line.top_ratio_x, width)
                line.top_y = int((line.top_ratio_y or 0.5) * height)
            line.update_top_ratios(width, height)

        for item in state["lines"]:
            line = line_dict[item["id"]]
            parent_id = item.get("parent_id"); snap_t = item.get("snap_t")
            if parent_id is not None and parent_id in line_dict:
                parent = line_dict[parent_id]
                line.parent = parent; line.snap_t = snap_t
                parent.children.append(line); parent.used_t_values.append(snap_t)
                line.follow_parent()

        self.renormalize_ratios()

        v = state.get("view", {})
        self.view_min = float(v.get("min", self.view_min))
        self.view_max = float(v.get("max", self.view_max))
        self.view_min_var.set(str(int(round(self.view_min * 100))))
        self.view_max_var.set(str(int(round(self.view_max * 100))))

        self.redraw_all()

        if "top_texts" in state:
            for frame in self.text_entries:
                entry = frame.winfo_children()[0]
                key = str(getattr(frame, "left_line_id", None))
                if key in state["top_texts"]:
                    entry.delete(0, tk.END); entry.insert(0, state["top_texts"][key])

        grp = state.get("group", {})
        bnds = grp.get("boundaries", []); txts = grp.get("texts", [])
        self.group_boundaries = [b for b in bnds if 1 <= b <= len(self.lines) - 2]
        self.group_text_cache = txts
        self._rebuild_group_row()
        self.master.after_idle(self._rebuild_group_row)
        self._update_status()
        self.line_count_var.set(str(len(self.lines)))

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.capture_state())
        state = self.undo_stack.pop()
        self.restore_state(state)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.capture_state())
        state = self.redo_stack.pop()
        self.restore_state(state)

    def save_state(self):
        self._snapshot_group_texts()
        data = {
            "lines": [],
            "top_texts": {},
            "group": {
                "boundaries": list(self.group_boundaries),
                "texts": [e.get() for e in self.group_entries] if self.group_entries else list(self.group_text_cache)
            },
            "view": {"min": self.view_min, "max": self.view_max}
        }
        for line in self.lines:
            data["lines"].append({
                "id": line.line_id,
                "base_ratio": line.base_ratio,
                "top_ratio_x": line.top_ratio_x,
                "top_ratio_y": line.top_ratio_y,
                "parent_id": line.parent.line_id if line.parent else None,
                "snap_t": line.snap_t
            })
        for frame in self.text_entries:
            entry = frame.winfo_children()[0]
            key = getattr(frame, "left_line_id", None)
            if key is not None:
                data["top_texts"][str(key)] = entry.get()

        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSONファイル", "*.json")])
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load_state(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSONファイル", "*.json")])
        if not filepath:
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.lines.clear()
        self.canvas.delete("all")

        line_dict = {}
        for item in data["lines"]:
            line = Line(self, self.canvas, item["base_ratio"], self.base_y_ratio, self.length, item["id"])
            line.top_ratio_x = item.get("top_ratio_x", 0.5)
            line.top_ratio_y = item.get("top_ratio_y", 0.5)
            line_dict[item["id"]] = line
            self.lines.append(line)

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        for line in self.lines:
            line.update_base_position(width, height)
            if line.top_ratio_x is None or line.top_ratio_y is None:
                line.top_x = line.base_x; line.top_y = line.base_y - self.length
            else:
                line.top_x = line.map_x(line.top_ratio_x, width)
                line.top_y = int((line.top_ratio_y or 0.5) * height)
            line.update_top_ratios(width, height)

        for item in data["lines"]:
            line = line_dict[item["id"]]
            parent_id = item.get("parent_id"); snap_t = item.get("snap_t")
            if parent_id is not None and parent_id in line_dict:
                parent = line_dict[parent_id]
                line.parent = parent; line.snap_t = snap_t
                parent.children.append(line); parent.used_t_values.append(snap_t)
                line.follow_parent()

        self.renormalize_ratios()

        v = data.get("view", {})
        self.view_min = float(v.get("min", 0.0))
        self.view_max = float(v.get("max", 1.0))
        self.view_min_var.set(str(int(round(self.view_min * 100))))
        self.view_max_var.set(str(int(round(self.view_max * 100))))

        self.redraw_all()

        for frame in self.text_entries:
            entry = frame.winfo_children()[0]
            key = str(getattr(frame, "left_line_id", None))
            if "top_texts" in data and key in data["top_texts"]:
                entry.delete(0, tk.END); entry.insert(0, data["top_texts"][key])

        grp = data.get("group", {})
        bnds = grp.get("boundaries", []); txts = grp.get("texts", [])
        self.group_boundaries = [b for b in bnds if 1 <= b <= len(self.lines) - 2]
        self.group_text_cache = txts
        self._rebuild_group_row()
        self.master.after_idle(self._rebuild_group_row)
        self._update_status()
        self.line_count_var.set(str(len(self.lines)))


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")
    app = SnapHierarchyApp(root, num_lines=6)
    root.mainloop()


