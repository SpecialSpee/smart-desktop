#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Desktop — Window Manager with Spaces
Production version with async updates, animations, logging, and desktop button
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import win32gui
import win32con
import ctypes
import math
import time
import json
import os
import logging
import threading
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# Try to import keyboard for global hotkeys (optional)
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

# ============================================================================
# CONFIGURATION & LOGGING
# ============================================================================

WATER_COLORS = {
    "bg": "#01052B",
    "surface": "#0d1f3c",
    "glass": "#1a3a5c",
    "glass_border": "#2a6496",
    "accent": "#00d4ff",
    "accent_glow": "#007a99",
    "text": "#e0f0ff",
    "text_dim": "#7a9bb5",
    "ripple": "#00d4ff",
    "main_ripple": "#ff8c42",
}

# Настройки
PANEL_WIDTH = 480
PANEL_HEIGHT_EXPANDED = 980
FLAG_SIZE = 40
CONFIG_FILE = "desktop_manager_config.json"
LOG_FILE = Path(__file__).parent / "smart_desktop.log"

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# RIPPLE MANAGER (Optimized with easing + cleanup)
# ============================================================================

class RippleManager:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.ripples = []
        self.active = False
        self._max_ripples = 50  # Prevent memory leaks

    def create_ripple(self, x, y, is_main=False, max_radius=80):
        if not self.canvas or len(self.ripples) >= self._max_ripples:
            return
        
        # Clean up old ripples if overflow
        if len(self.ripples) > self._max_ripples - 4:
            for r in self.ripples[:4]:
                try:
                    self.canvas.delete(r["id"])
                except:
                    pass
            self.ripples = self.ripples[4:]
        
        color = WATER_COLORS["main_ripple"] if is_main else WATER_COLORS["ripple"]
        for i in range(2):
            try:
                rid = self.canvas.create_oval(
                    x-4, y-4, x+4, y+4, 
                    outline=color, width=max(1, 2-i), state="hidden"
                )
                self.ripples.append({
                    "id": rid, 
                    "x": x, 
                    "y": y, 
                    "radius": 4,
                    "max_radius": max_radius, 
                    "color": color,
                    "start_time": time.time() * 1000 + i * 60,
                    "alpha": 1.0
                })
            except Exception as e:
                logger.debug(f"Ripple create error: {e}")
        
        if not self.active:
            self.active = True
            self._animate()

    def _animate(self):
        if not self.ripples or not self.canvas:
            self.active = False
            return
        
        now = time.time() * 1000
        to_remove = []
        
        for r in self.ripples:
            elapsed = now - r["start_time"]
            if elapsed < 0:
                continue
            
            progress = min(elapsed / 500, 1.0)
            
            if progress >= 1:
                to_remove.append(r)
                try:
                    self.canvas.delete(r["id"])
                except:
                    pass
                continue
            
            # ✅ Cubic ease-out for smooth animation
            eased = 1 - math.pow(1 - progress, 3)
            radius = 4 + (r["max_radius"] - 4) * eased
            alpha = 1.0 - progress
            
            try:
                self.canvas.coords(
                    r["id"], 
                    r["x"]-radius, r["y"]-radius, 
                    r["x"]+radius, r["y"]+radius
                )
                if alpha < 0.3:
                    self.canvas.itemconfig(r["id"], state="hidden")
                else:
                    self.canvas.itemconfig(r["id"], state="normal")
            except Exception as e:
                logger.debug(f"Ripple animate error: {e}")
                to_remove.append(r)
        
        for r in to_remove:
            try:
                self.ripples.remove(r)
            except:
                pass
        
        if self.ripples:
            self.canvas.after(16, self._animate)
        else:
            self.active = False

    def cleanup(self):
        """Clear all ripples on exit"""
        for r in self.ripples:
            try:
                self.canvas.delete(r["id"])
            except:
                pass
        self.ripples.clear()
        self.active = False


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class SmartDesktop(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Smart Desktop")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # Dynamic screen metrics
        self._update_screen_metrics()
        
        self.panel_expanded = False
        self._position_flag()
        
        self.configure(fg_color=WATER_COLORS["bg"])
        self.attributes("-alpha", 0.99)

        # Double buffering for canvas (reduce flicker)
        self.bg_canvas = None  # Created after window init

        # Data
        self.spaces: List[Dict] = [{"windows": []} for _ in range(4)]
        self.cur_space = 0
        self.available: List[Tuple[int, str]] = []
        self.card_widgets: List[ctk.CTkFrame] = []
        
        # Cache for window rects
        self._window_rect_cache: Dict[int, Tuple] = {}
        self._cache_timestamp = 0
        self._cache_ttl = 0.5
        
        self._load_config()

        # Initialize UI components
        self._init_canvas()
        self._init_flag_button()
        self._init_header()
        self._init_content()
        self._init_status()
        self._init_hotkeys()
        
        # Start async window refresh
        self.after(200, self._refresh_windows_async)
        
        logger.info("Smart Desktop initialized")

    def _init_canvas(self):
        """Initialize background canvas with double buffering"""
        self.bg_canvas = tk.Canvas(
            self, bg=WATER_COLORS["bg"], 
            highlightthickness=0, bd=0
        )
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # Enable double buffering (Windows-specific)
        try:
            self.bg_canvas.config(doublebuffer=True)
        except:
            pass  # Fallback if not supported
        self.ripple_manager = RippleManager(self.bg_canvas)

    def _init_flag_button(self):
        """Initialize the flag toggle button"""
        self.flag_btn = ctk.CTkButton(
            self, text="🪟", width=FLAG_SIZE, height=FLAG_SIZE,
            font=ctk.CTkFont(size=22), fg_color=WATER_COLORS["accent"],
            hover_color=WATER_COLORS["accent_glow"], text_color="#000",
            corner_radius=12, command=self._toggle_panel
        )
        self.flag_btn.place(x=0, y=0)
        self._add_hover_effect(self.flag_btn, WATER_COLORS["accent"], WATER_COLORS["accent_glow"])

    def _init_header(self):
        """Initialize header frame (visible when expanded)"""
        self.header_frame = ctk.CTkFrame(
            self, fg_color=WATER_COLORS["surface"], 
            height=52, width=PANEL_WIDTH, corner_radius=0
        )
        
        # Close button
        self.close_btn = ctk.CTkButton(
            self.header_frame, text=">>", width=36, height=36,
            font=ctk.CTkFont(size=16, weight="bold"), fg_color="#4709f0",
            hover_color="#c0392b", text_color="#fff",
            corner_radius=8, command=self._collapse_panel
        )
        self.close_btn.place(x=10, y=8)
        self._add_hover_effect(self.close_btn, "#4709f0", "#c0392b")
        
        # Space buttons
        self.space_btns = []
        planet_icons = ["🌍", "🌍", "🌍", "🌍"]
        for i in range(4):
            btn = ctk.CTkButton(
                self.header_frame, text=f"{planet_icons[i]} {i+1}", width=50, height=38,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=WATER_COLORS["accent"] if i == 0 else WATER_COLORS["glass"],
                hover_color=WATER_COLORS["glass_border"],
                text_color="#000" if i == 0 else WATER_COLORS["text"],
                corner_radius=8, command=lambda idx=i: self._switch_space(idx)
            )
            btn.place(x=60 + i * 52, y=7)
            self.space_btns.append(btn)
            self._add_hover_effect(btn, 
                WATER_COLORS["accent"] if i == 0 else WATER_COLORS["glass"],
                WATER_COLORS["glass_border"]
            )
        
        # 💾 Save button
        save_btn = ctk.CTkButton(
            self.header_frame, text="💾", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color=WATER_COLORS["glass_border"],
            text_color=WATER_COLORS["accent"], corner_radius=8, font=ctk.CTkFont(size=16),
            command=self._save_layout
        )
        save_btn.place(x=PANEL_WIDTH - 110, y=7)
        self._add_hover_effect(save_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # ✓ Apply button
        apply_btn = ctk.CTkButton(
            self.header_frame, text="✓", width=42, height=38,
            fg_color=WATER_COLORS["accent"], hover_color=WATER_COLORS["accent_glow"],
            text_color="#000", corner_radius=8, font=ctk.CTkFont(size=18, weight="bold"),
            command=self._apply_layout
        )
        apply_btn.place(x=PANEL_WIDTH - 55, y=7)
        self._add_hover_effect(apply_btn, WATER_COLORS["accent"], WATER_COLORS["accent_glow"])
        
        # 🖥️ Show Desktop button (USER REQUEST)
        self.desktop_btn = ctk.CTkButton(
            self.header_frame, text="🖥️", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color="#2a6496",
            text_color=WATER_COLORS["accent"], corner_radius=8, 
            font=ctk.CTkFont(size=16),
            command=self._show_desktop
        )
        self.desktop_btn.place(x=PANEL_WIDTH - 180, y=7)
        self._add_hover_effect(self.desktop_btn, WATER_COLORS["glass"], "#2a6496")

    def _init_content(self):
        """Initialize content frame"""
        self.content_frame = ctk.CTkFrame(
            self, fg_color=WATER_COLORS["bg"], 
            width=PANEL_WIDTH, height=PANEL_HEIGHT_EXPANDED - 52
        )
        
        ctk.CTkLabel(
            self.content_frame, text=" Окна (✓ — добавить, ⭐ — главное):", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=WATER_COLORS["text_dim"], fg_color="transparent",
            width=PANEL_WIDTH - 20, height=24
        ).place(x=10, y=8)
        
        self.windows_scroll = ctk.CTkScrollableFrame(
            self.content_frame, fg_color="transparent",
            width=PANEL_WIDTH - 20, height=PANEL_HEIGHT_EXPANDED - 140
        )
        self.windows_scroll.place(x=10, y=35)
        
        # Hotkey hint frame
        hotkey_frame = ctk.CTkFrame(
            self.content_frame, fg_color=WATER_COLORS["surface"], 
            height=45, width=PANEL_WIDTH - 20, corner_radius=8
        )
        hotkey_frame.place(x=10, y=PANEL_HEIGHT_EXPANDED - 125)
        
        ctk.CTkLabel(
            hotkey_frame, text="⌨️ Горячие клавиши:", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=WATER_COLORS["accent"], fg_color="transparent"
        ).place(x=10, y=0)
        
        ctk.CTkLabel(
            hotkey_frame, 
            text="F1 — открыть/закрыть  •  F2 — расставить  •  F3 — сохранить  •  ctrl + D — рабочий стол", 
            font=ctk.CTkFont(size=9),
            text_color=WATER_COLORS["text"], fg_color="transparent"
        ).place(x=10, y=20)

    def _init_status(self):
        """Initialize status bar"""
        self.status = ctk.CTkLabel(
            self, text="🚀 Готов", anchor="center", font=ctk.CTkFont(size=9),
            text_color=WATER_COLORS["text_dim"], fg_color="transparent",
            width=PANEL_WIDTH, height=20
        )
        self.status.place(x=0, y=PANEL_HEIGHT_EXPANDED - 20)

    def _init_hotkeys(self):
        """Initialize keyboard shortcuts"""
        self.bind("<F1>", lambda e: self._toggle_panel())
        self.bind("<F2>", lambda e: self._apply_layout())
        self.bind("<F3>", lambda e: self._save_layout())
        self.bind("<Escape>", lambda e: self._collapse_panel())
        self.bind("<Control-d>", lambda e: self._show_desktop())
        
        # Global hotkeys if keyboard library available
        if KEYBOARD_AVAILABLE:
            self._setup_global_hotkeys()

    def _setup_global_hotkeys(self):
        """Register global hotkeys via keyboard library"""
        try:
            keyboard.add_hotkey('ctrl+alt+f1', self._toggle_panel, suppress=False)
            keyboard.add_hotkey('ctrl+alt+f2', self._apply_layout, suppress=False)
            keyboard.add_hotkey('ctrl+alt+f3', self._save_layout, suppress=False)
            keyboard.add_hotkey('ctrl+alt+d', self._show_desktop, suppress=False)
            logger.info("Global hotkeys registered")
        except Exception as e:
            logger.warning(f"Could not register global hotkeys: {e}")

    def _add_hover_effect(self, widget, base_color, hover_color):
        """Add hover color effect to any widget"""
        def on_enter(e):
            try:
                widget.configure(fg_color=hover_color)
            except:
                pass
        def on_leave(e):
            try:
                widget.configure(fg_color=base_color)
            except:
                pass
        try:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
        except:
            pass  # Some widgets may not support binding

    def _update_screen_metrics(self):
        """Update screen dimensions dynamically"""
        try:
            user32 = ctypes.windll.user32
            self.SW = user32.GetSystemMetrics(0)
            self.SH = user32.GetSystemMetrics(1)
        except Exception as e:
            logger.error(f"Screen metrics error: {e}")
            self.SW, self.SH = 1920, 1080  # Fallback

    def _position_flag(self):
        """Position flag button in top-right corner"""
        self._update_screen_metrics()
        px = self.SW - FLAG_SIZE
        py = 50
        self.geometry(f"{FLAG_SIZE}x{FLAG_SIZE}+{px}+{py}")

    def _toggle_panel(self):
        """Toggle panel expanded/collapsed state"""
        if self.panel_expanded:
            self._collapse_panel()
        else:
            self._expand_panel()

    def _expand_panel(self):
        """Expand panel with smooth animation"""
        if self.panel_expanded:
            return
        self.panel_expanded = True
        
        self._update_screen_metrics()
        self.flag_btn.place_forget()
        self.header_frame.place(x=0, y=0)
        self.content_frame.place(x=0, y=52)
        
        # Adaptive height
        max_height = self.SH - 100
        panel_height = min(PANEL_HEIGHT_EXPANDED, max_height)
        
        # Position: right side, vertically centered
        px = self.SW - PANEL_WIDTH
        py = max(50, (self.SH - panel_height) // 2)
        
        self.geometry(f"{PANEL_WIDTH}x{panel_height}+{px}+{py}")
        
        # Adjust scrollable area
        scroll_height = panel_height - 140
        self.windows_scroll.configure(height=max(200, scroll_height))
        self.windows_scroll.place(x=10, y=35)
        
        # Update hotkey frame position
        hotkey_y = panel_height - 125
        for widget in self.content_frame.winfo_children():
            if isinstance(widget, ctk.CTkFrame) and widget.winfo_y() > PANEL_HEIGHT_EXPANDED - 200:
                widget.place(y=hotkey_y)
        
        self.status.place(y=panel_height - 20)
        
        # Smooth alpha fade-in
        self._animate_alpha(0.0, 0.99, duration=200)
        
        self._refresh_windows_async()
        self.ripple_manager.create_ripple(PANEL_WIDTH // 2, 20, is_main=True, max_radius=60)
        logger.info("Panel expanded")

    def _collapse_panel(self):
        """Collapse panel with smooth animation"""
        if not self.panel_expanded:
            return
        
        # Fade out first, then collapse
        self._animate_alpha(0.99, 0.0, duration=150, 
                          on_complete=self._finish_collapse)
        logger.info("Panel collapsing")

    def _animate_alpha(self, start, end, duration, on_complete=None):
        """Smooth alpha transition animation"""
        steps = 10
        delay = max(10, duration // steps)
        delta = (end - start) / steps
        current = [start]  # Use list for mutable reference in closure
        
        def step():
            current[0] += delta
            alpha = max(0.0, min(1.0, current[0]))
            self.attributes("-alpha", alpha)
            
            if (delta > 0 and current[0] < end) or (delta < 0 and current[0] > end):
                self.after(delay, step)
            else:
                self.attributes("-alpha", end)
                if on_complete:
                    on_complete()
        
        step()

    def _finish_collapse(self):
        """Complete collapse after fade animation"""
        self.panel_expanded = False
        self.header_frame.place_forget()
        self.content_frame.place_forget()
        self.flag_btn.place(x=0, y=0)
        self._position_flag()
        self.attributes("-alpha", 0.99)
        logger.info("Panel collapsed")

    def _switch_space(self, idx):
        """Switch between workspace tabs"""
        if self.cur_space == idx:
            return
        self.cur_space = idx
        for i, btn in enumerate(self.space_btns):
            btn.configure(
                fg_color=WATER_COLORS["accent"] if i == idx else WATER_COLORS["glass"],
                text_color="#000" if i == idx else WATER_COLORS["text"]
            )
        self._render_windows_list()
        self.ripple_manager.create_ripple(300, 20, is_main=False, max_radius=40)
        logger.info(f"Switched to space {idx + 1}")

    def _refresh_windows_async(self):
        """Non-blocking window list refresh via threading"""
        def worker():
            result = []
            def enum_callback(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = win32gui.GetWindowText(hwnd)
                    if not title or len(title.strip()) < 2:
                        return True
                    
                    lower = (title + win32gui.GetClassName(hwnd)).lower()
                    skip = ["taskbar", "program manager", "shell_traywnd", "search", 
                           "copilot", "windows shell", "seth", "application frame host",
                           "settings", "start", "cortana", "action center", "notification"]
                    if any(kw in lower for kw in skip):
                        return True
                    if title.lower() in ["settings", "start", ""]:
                        return True
                    result.append((hwnd, title))
                except Exception as e:
                    logger.debug(f"Enum window error: {e}")
                return True
            
            win32gui.EnumWindows(enum_callback, None)
            # Return to main thread
            self.after(0, lambda: self._update_available_windows(result))
        
        threading.Thread(target=worker, daemon=True).start()

    def _update_available_windows(self, windows_list):
        """Update available windows list in main thread"""
        self.available = windows_list
        if self.panel_expanded:
            self._render_windows_list()
        self.status.configure(text=f"🔍 Найдено: {len(windows_list)}")

    def _show_desktop(self):
        """Minimize all windows to show desktop (USER REQUEST)"""
        try:
            # Method 1: Win API broadcast (fastest)
            hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
            if hwnd:
                win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 419, 0)
            
            self.status.configure(text="🖥️ Рабочий стол")
            self.ripple_manager.create_ripple(PANEL_WIDTH // 2, 20, is_main=True, max_radius=60)
            logger.info("Show desktop triggered")
            
        except Exception as e:
            logger.error(f"Show desktop error: {e}")
            # Fallback: enumerate and minimize
            def enum_minimize(hwnd, _):
                try:
                    if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                except:
                    pass
                return True
            win32gui.EnumWindows(enum_minimize, None)

    def _restore_windows(self):
        """Restore windows from current space"""
        space = self.spaces[self.cur_space]
        restored = 0
        for win in space["windows"]:
            try:
                if win32gui.IsWindow(win["hwnd"]):
                    win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
                    restored += 1
            except:
                pass
        self.status.configure(text=f"✅ Восстановлено: {restored}")
        logger.info(f"Restored {restored} windows")

    def _refresh_windows(self):
        """Synchronous refresh (fallback)"""
        self.available = []
        
        def enum_callback(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title or len(title.strip()) < 2:
                    return True
                
                lower = (title + win32gui.GetClassName(hwnd)).lower()
                skip = ["taskbar", "program manager", "shell_traywnd", "search", 
                       "copilot", "windows shell", "seth", "application frame host",
                       "settings", "start", "cortana", "action center", "notification"]
                if any(kw in lower for kw in skip):
                    return True
                if title.lower() in ["settings", "start", ""]:
                    return True
                
                self.available.append((hwnd, title))
            except Exception as e:
                logger.debug(f"Enum error: {e}")
            return True
        
        win32gui.EnumWindows(enum_callback, None)
        self._render_windows_list()

    def _render_windows_list(self):
        """Render the list of available windows"""
        for w in self.windows_scroll.winfo_children():
            w.destroy()
        self.card_widgets = []
        
        space = self.spaces[self.cur_space]
        space_hwnds = {w["hwnd"] for w in space["windows"]}
        row_width = PANEL_WIDTH - 20
        
        for hwnd, title in self.available:
            in_space = hwnd in space_hwnds
            win_data = next((w for w in space["windows"] if w["hwnd"] == hwnd), None)
            is_main = win_data.get("is_main", False) if win_data else False
            
            bg_color = WATER_COLORS["glass"] if in_space else WATER_COLORS["surface"]
            
            # Fixed height row
            row = ctk.CTkFrame(self.windows_scroll, fg_color=bg_color, 
                              corner_radius=8, height=44, width=row_width)
            row.pack(fill=tk.X, pady=2, padx=0)
            row.pack_propagate(False)
            
            display = title if len(title) <= 35 else title[:32] + "..."
            
            # Window title label
            label = ctk.CTkLabel(row, text=display, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold" if in_space else "normal"), 
                         text_color=WATER_COLORS["accent"] if in_space else WATER_COLORS["text"],
                         width=row_width - 90, height=44)
            label.place(x=10, y=0)
            
            # Check button (always visible)
            check_text = "✓" if in_space else "🟦"
            check_color = WATER_COLORS["accent"] if in_space else WATER_COLORS["text_dim"]
            
            btn_check = ctk.CTkButton(row, text=check_text, width=38, height=36,
                          fg_color="transparent", hover_color=WATER_COLORS["glass"],
                          text_color=check_color, corner_radius=6, 
                          font=ctk.CTkFont(size=16, weight="bold"),
                          command=lambda h=hwnd, t=title: self._toggle_in_space(h, t)
                         )
            btn_check.place(x=row_width - 78, y=4)
            self._add_hover_effect(btn_check, "transparent", WATER_COLORS["glass"])
            
            # Star button (only if in space)
            if in_space:
                main_text = "⭐" if is_main else "☆"
                btn_main = ctk.CTkButton(row, text=main_text, width=34, height=36,
                              fg_color="transparent", hover_color=WATER_COLORS["glass_border"],
                              text_color=WATER_COLORS["accent"] if is_main else WATER_COLORS["text_dim"],
                              corner_radius=6, font=ctk.CTkFont(size=13),
                              command=lambda h=hwnd: self._toggle_main(h)
                             )
                btn_main.place(x=row_width - 36, y=4)
                self._add_hover_effect(btn_main, "transparent", WATER_COLORS["glass_border"])
            
            self.card_widgets.append(row)

    def _toggle_in_space(self, hwnd, title):
        """Toggle window inclusion in current space"""
        space = self.spaces[self.cur_space]
        space_hwnds = [w["hwnd"] for w in space["windows"]]
        
        if hwnd in space_hwnds:
            space["windows"] = [w for w in space["windows"] if w["hwnd"] != hwnd]
            logger.info(f"Removed from space: {title}")
        else:
            if len(space["windows"]) >= 10:
                messagebox.showwarning("Лимит", "Максимум 10 окон на пространство!")
                return
            space["windows"].append({
                "hwnd": hwnd, 
                "title": title, 
                "is_main": False, 
                "saved_rect": None
            })
            logger.info(f"Added to space: {title}")
        
        self._save_config()
        self._render_windows_list()

    def _toggle_main(self, hwnd):
        """Toggle main window flag"""
        space = self.spaces[self.cur_space]
        for win in space["windows"]:
            if win["hwnd"] == hwnd:
                win["is_main"] = not win["is_main"]
                logger.info(f"Main flag toggled: {win['title']} = {win['is_main']}")
                break
        self._save_config()
        self._render_windows_list()

    def _get_window_rect_cached(self, hwnd):
        """Cached window rect lookup for performance"""
        now = time.time()
        if now - self._cache_timestamp > self._cache_ttl:
            self._window_rect_cache.clear()
            self._cache_timestamp = now
        
        if hwnd not in self._window_rect_cache:
            try:
                rect = win32gui.GetWindowRect(hwnd)
                self._window_rect_cache[hwnd] = rect
            except Exception as e:
                logger.debug(f"GetWindowRect error: {e}")
                return None
        return self._window_rect_cache[hwnd]

    def _save_layout(self):
        """Save current window positions"""
        space = self.spaces[self.cur_space]
        saved = 0
        
        for win in space["windows"]:
            hwnd = win["hwnd"]
            try:
                if not win32gui.IsWindow(hwnd):
                    continue
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                win["saved_rect"] = (left, top, right - left, bottom - top)
                saved += 1
            except Exception as e:
                logger.warning(f"Could not save position for {win.get('title', 'unknown')}: {e}")
        
        if saved > 0:
            self._save_config()
            self.status.configure(text=f"💾 Сохранено: {saved}")
            self.ripple_manager.create_ripple(PANEL_WIDTH // 2, 20, is_main=True, max_radius=60)
            self._render_windows_list()
            logger.info(f"Saved positions for {saved} windows")
        else:
            messagebox.showinfo("Инфо", "Нет окон для сохранения!")
            logger.warning("Save layout: no windows to save")

    def _save_config(self):
        """Save configuration with backup and validation"""
        try:
            # Create backup
            if os.path.exists(CONFIG_FILE):
                backup = CONFIG_FILE + ".bak"
                with open(CONFIG_FILE, "r", encoding="utf-8") as src:
                    with open(backup, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
            
            # Validate and prepare data
            data = []
            for space in self.spaces:
                space_data = []
                for win in space["windows"]:
                    # Skip windows that no longer exist
                    if not win32gui.IsWindow(win["hwnd"]):
                        logger.warning(f"Window no longer exists: {win['title']}")
                        continue
                    win_copy = win.copy()
                    if win_copy.get("saved_rect"):
                        win_copy["saved_rect"] = list(win_copy["saved_rect"])
                    space_data.append(win_copy)
                data.append({"windows": space_data})
            
            # Atomic write
            temp_file = CONFIG_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, CONFIG_FILE)
            
            logger.info(f"Config saved: {sum(len(s['windows']) for s in data)} windows")
            
        except Exception as e:
            logger.error(f"Config save failed: {e}", exc_info=True)
            # Attempt restore from backup
            if os.path.exists(CONFIG_FILE + ".bak"):
                try:
                    os.replace(CONFIG_FILE + ".bak", CONFIG_FILE)
                    logger.warning("Config restored from backup")
                except Exception as restore_err:
                    logger.error(f"Backup restore failed: {restore_err}")

    def _load_config(self):
        """Load configuration from file"""
        if not os.path.exists(CONFIG_FILE):
            logger.info("No config file found, starting fresh")
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for i, space_data in enumerate(data[:4]):
                for win in space_data.get("windows", []):
                    if win.get("saved_rect"):
                        win["saved_rect"] = tuple(win["saved_rect"])
                    # Only add if window still exists
                    if win32gui.IsWindow(win["hwnd"]):
                        self.spaces[i]["windows"].append(win)
                    else:
                        logger.warning(f"Skipping stale window: {win.get('title', 'unknown')}")
            
            logger.info(f"Config loaded: {sum(len(s['windows']) for s in self.spaces)} windows")
        except Exception as e:
            logger.error(f"Config load failed: {e}", exc_info=True)

    def _apply_layout(self):
        """Apply saved window layout"""
        space = self.spaces[self.cur_space]
        if not space["windows"]:
            messagebox.showinfo("Инфо", "Добавьте окна галочкой ✓")
            return
        
        logger.info(f"Applying layout for space {self.cur_space + 1}")
        
        # Hide other spaces
        for i, sp in enumerate(self.spaces):
            if i == self.cur_space:
                continue
            for win in sp["windows"]:
                try:
                    if win32gui.IsWindowVisible(win["hwnd"]):
                        win32gui.ShowWindow(win["hwnd"], win32con.SW_MINIMIZE)
                except Exception as e:
                    logger.debug(f"Minimize error: {e}")
        
        time.sleep(0.03)  # Minimal delay
        
        # Restore windows in current space
        for win in space["windows"]:
            try:
                win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
            except Exception as e:
                logger.debug(f"Restore error: {e}")
        
        # Get work area dynamically
        try:
            work_left, work_top, work_right, work_bottom = win32gui.SystemParametersInfo(
                win32con.SPI_GETWORKAREA
            )
        except Exception as e:
            logger.warning(f"Work area detection failed: {e}")
            work_left, work_top = 0, 0
            work_right, work_bottom = self.SW, self.SH
        
        work_width = work_right - work_left
        work_height = work_bottom - work_top
        gap = 12
        MIN_W, MIN_H = 200, 150
        
        def move_window(hwnd, x, y, w, h):
            """Move window with boundary checks"""
            try:
                if not win32gui.IsWindow(hwnd):
                    return
                
                w = max(w, MIN_W)
                h = max(h, MIN_H)
                abs_x = work_left + int(x)
                abs_y = work_top + int(y)
                
                # Strict boundary enforcement
                abs_x = max(work_left, min(abs_x, work_right - w))
                abs_y = max(work_top, min(abs_y, work_bottom - h))
                
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.005)  # Minimal delay between moves
                win32gui.MoveWindow(hwnd, abs_x, abs_y, int(w), int(h), True)
            except Exception as e:
                logger.error(f"MoveWindow failed for hwnd {hwnd}: {e}")

        # Separate saved vs auto-layout windows
        saved = [w for w in space["windows"] if w.get("saved_rect")]
        auto = [w for w in space["windows"] if not w.get("saved_rect")]
        
        # Apply saved positions first
        for win in saved:
            x, y, w, h = win["saved_rect"]
            move_window(win["hwnd"], x, y, w, h)
        
        # Auto-layout remaining windows
        n = len(auto)
        main_win = next((w for w in auto if w.get("is_main")), None)
        regular_wins = [w for w in auto if not w.get("is_main")]
        
        if n == 0:
            pass
        elif n == 1:
            move_window(auto[0]["hwnd"], gap, gap, work_width - gap*2, work_height - gap*2)
        elif n == 2:
            if main_win:
                mw = int(work_width * 0.65)
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                other = regular_wins[0] if regular_wins else auto[1]
                move_window(other["hwnd"], mw, gap, work_width - mw - gap*2, work_height - gap*2)
            else:
                w = (work_width - gap * 3) // 2
                move_window(auto[0]["hwnd"], gap, gap, w, work_height - gap*2)
                move_window(auto[1]["hwnd"], gap + w + gap, gap, w, work_height - gap*2)
        elif n == 3:
            if main_win:
                mw = int(work_width * 0.60)
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                rw = work_width - mw - gap * 2
                rh = (work_height - gap * 3) // 2
                if len(regular_wins) >= 1:
                    move_window(regular_wins[0]["hwnd"], mw, gap, rw, rh)
                if len(regular_wins) >= 2:
                    move_window(regular_wins[1]["hwnd"], mw, gap + rh + gap, rw, rh)
            else:
                w = (work_width - gap * 3) // 2
                h_top = int(work_height * 0.55)
                move_window(auto[0]["hwnd"], gap, gap, w, h_top - gap)
                move_window(auto[1]["hwnd"], gap + w + gap, gap, w, h_top - gap)
                move_window(auto[2]["hwnd"], gap, h_top, work_width - gap*2, work_height - h_top - gap)
        elif n == 4:
            if main_win:
                mw = work_width // 2
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                rw = (work_width - mw - gap * 4) // 2
                rh = (work_height - gap * 3) // 2
                for i, win in enumerate(regular_wins[:3]):
                    if i == 0:
                        move_window(win["hwnd"], mw, gap, rw, rh)
                    elif i == 1:
                        move_window(win["hwnd"], mw + gap + rw, gap, rw, rh)
                    elif i == 2:
                        move_window(win["hwnd"], mw + gap, gap + rh + gap, rw * 2 + gap, rh)
            else:
                w = (work_width - gap * 3) // 2
                h = (work_height - gap * 3) // 2
                coords = [
                    (gap, gap, w, h),
                    (gap + w + gap, gap, w, h),
                    (gap, gap + h + gap, w, h),
                    (gap + w + gap, gap + h + gap, w, h)
                ]
                for i, win in enumerate(auto):
                    move_window(win["hwnd"], *coords[i])
        elif n >= 5:
            if main_win:
                mw = int(work_width * 0.60)
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                rw = work_width - mw - gap * 2
                rh = work_height - gap * 2
                cols = 2
                rows = math.ceil(len(regular_wins) / cols)
                cell_w = (rw - gap * (cols + 1)) // cols
                cell_h = (rh - gap * (rows + 1)) // rows
                for i, win in enumerate(regular_wins):
                    r, c = divmod(i, cols)
                    x = mw + gap + c * (cell_w + gap)
                    y = gap + r * (cell_h + gap)
                    move_window(win["hwnd"], x, y, cell_w, cell_h)
            else:
                cols = 3
                rows = math.ceil(n / cols)
                cell_w = (work_width - gap * (cols + 1)) // cols
                cell_h = (work_height - gap * (rows + 1)) // rows
                for i, win in enumerate(auto):
                    r, c = divmod(i, cols)
                    x = gap + c * (cell_w + gap)
                    y = gap + r * (cell_h + gap)
                    move_window(win["hwnd"], x, y, cell_w, cell_h)

        self.status.configure(text=f"✅ Расставлено: {len(space['windows'])}")
        self.ripple_manager.create_ripple(PANEL_WIDTH // 2, 20, is_main=True, max_radius=60)
        self.after(1000, self._collapse_panel)
        logger.info(f"Layout applied: {len(space['windows'])} windows positioned")

    def destroy(self):
        """Cleanup on exit"""
        logger.info("Smart Desktop shutting down")
        
        # Unregister global hotkeys
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except:
                pass
        
        # Cleanup ripples
        self.ripple_manager.cleanup()
        
        # Save config
        self._save_config()
        
        # Restore all windows to normal state
        for space in self.spaces:
            for win in space["windows"]:
                try:
                    if win32gui.IsWindow(win["hwnd"]):
                        win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
                except:
                    pass
        
        super().destroy()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Enable High DPI scaling (Windows)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    # Set customtkinter appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    logger.info("=== Smart Desktop Starting ===")
    app = SmartDesktop()
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
    finally:
        logger.info("=== Smart Desktop Exited ===")