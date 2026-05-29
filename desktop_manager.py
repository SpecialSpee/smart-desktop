#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Desktop v1.2 — Window Manager with Spaces
Production version with:
- Real-time window monitoring
- Configurable limits & hotkeys
- Auto-close panel (FIXED timing)
- Full settings dialog with themes
- "All Windows" mode button
- Editable hotkeys in settings
- Cross-platform ready architecture
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
import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# Try to import keyboard for global hotkeys (optional)
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("keyboard module not available — global hotkeys disabled")

# ============================================================================
# DEFAULT SETTINGS & CONFIGURATION
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

ORIGINAL_WATER_COLORS = WATER_COLORS.copy()

DARK_COLORS = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "glass": "#0f3460",
    "glass_border": "#533483",
    "accent": "#e94560",
    "accent_glow": "#c73e54",
    "text": "#eaeaea",
    "text_dim": "#a0a0a0",
    "ripple": "#e94560",
    "main_ripple": "#ffd700",
}

LIGHT_COLORS = {
    "bg": "#f0f4f8",
    "surface": "#d9e2ec",
    "glass": "#bcccdc",
    "glass_border": "#9fb3c8",
    "accent": "#0077b6",
    "accent_glow": "#005f8a",
    "text": "#102a43",
    "text_dim": "#627d98",
    "ripple": "#0077b6",
    "main_ripple": "#ff6b35",
}

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    "ui": {
        "theme": "water",
        "panel_position": "right",
        "animation_speed": 1.0,
        "colors": None,
    },
    "behavior": {
        "max_spaces": 4,
        "max_windows_per_space": 15,
        "auto_close_delay": 15,
        "auto_close_after_apply": 3,  # ✅ НОВЫЙ: задержка после применения расстановки
        "window_monitor_interval": 2000,
        "minimize_other_spaces": True,
    },
    "hotkeys": {
        "toggle_panel": "F1",
        "apply_layout": "F2",
        "save_layout": "F3",
        "show_desktop": "Ctrl+D",
        "switch_spaces": ["Ctrl+F1", "Ctrl+F2", "Ctrl+F3", "Ctrl+F4"],
        "all_windows_mode": "Ctrl+A",  # ✅ НОВЫЙ: хоткей для режима "все окна"
    }
}

# Пути
CONFIG_FILE = "desktop_manager_config.json"
SETTINGS_FILE = "smart_desktop_settings.json"
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
# HOTKEY UTILS
# ============================================================================

def normalize_hotkey(key: str) -> str:
    """Нормализует строку хоткея к единому формату"""
    key = key.strip().lower()
    # Заменяем алиасы
    key = key.replace("ctrl", "control")
    key = key.replace("win", "windows")
    key = key.replace("cmd", "windows")
    # Убираем лишние пробелы
    key = re.sub(r'\s*\+\s*', '+', key)
    return key

def parse_hotkey(key: str):
    """Парсит строку хоткея в формат для keyboard.add_hotkey"""
    return normalize_hotkey(key)

def format_hotkey_display(key: str) -> str:
    """Форматирует хоткей для отображения в UI"""
    parts = key.split('+')
    formatted = []
    for p in parts:
        p = p.strip().capitalize()
        if p == "Control":
            formatted.append("Ctrl")
        elif p == "Windows":
            formatted.append("Win")
        else:
            formatted.append(p.upper() if len(p) == 1 else p)
    return '+'.join(formatted)


# ============================================================================
# RIPPLE MANAGER (Optimized)
# ============================================================================

class RippleManager:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.ripples = []
        self.active = False
        self._max_ripples = 10

    def create_ripple(self, x, y, is_main=False, max_radius=80):
        if not self.canvas or len(self.ripples) >= self._max_ripples:
            return
        
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
                    "id": rid, "x": x, "y": y, "radius": 4,
                    "max_radius": max_radius, "color": color,
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
            
            eased = 1 - math.pow(1 - progress, 3)
            radius = 4 + (r["max_radius"] - 4) * eased
            alpha = 1.0 - progress
            
            try:
                self.canvas.coords(
                    r["id"], r["x"]-radius, r["y"]-radius,
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
        for r in self.ripples:
            try:
                self.canvas.delete(r["id"])
            except:
                pass
        self.ripples.clear()
        self.active = False


# ============================================================================
# SETTINGS DIALOG — С РАБОЧИМИ ХОТКЕЯМИ
# ============================================================================

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, settings: dict, on_save, on_preview=None):
        super().__init__(parent)
        self.settings = json.loads(json.dumps(settings))
        self.on_save = on_save
        self.on_preview = on_preview
        self._recording_hotkey = None  # Для режима записи хоткея
        
        self.title("⚙️ Настройки Smart Desktop")
        self.geometry("520x700")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        self._build_ui()
        logger.info("Settings dialog opened")

    def _build_ui(self):
        title_label = ctk.CTkLabel(
            self, text="⚙️ Настройки",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(15, 10))
        
        tabview = ctk.CTkTabview(self, width=500, height=520)
        tabview.pack(padx=10, pady=10)
        
        ui_tab = tabview.add("🎨 Интерфейс")
        behavior_tab = tabview.add("⚡ Поведение")
        hotkeys_tab = tabview.add("⌨️ Горячие клавиши")
        
        self._build_ui_tab(ui_tab)
        self._build_behavior_tab(behavior_tab)
        self._build_hotkeys_tab(hotkeys_tab)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ctk.CTkButton(
            btn_frame, text="💾 Сохранить",
            command=self._save, width=120,
            fg_color="#27ae60", hover_color="#219a52"
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame, text="❌ Отмена",
            command=self.destroy, width=120,
            fg_color="#7f8c8d", hover_color="#95a5a6"
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame, text="🔄 Сброс",
            command=self._reset, width=120,
            fg_color="#c0392b", hover_color="#e74c3c"
        ).pack(side="left", padx=5)

    def _build_ui_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, width=480, height=460)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkLabel(
            scroll, text="🎨 Тема оформления:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(10, 5))
        
        theme_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        theme_frame.pack(fill="x", padx=10, pady=5)
        
        self.theme_var = tk.StringVar(value=self.settings["ui"]["theme"])
        themes = [
            ("💧 Водяная (синяя)", "water", WATER_COLORS["bg"]),
            ("🌙 Тёмная", "dark", DARK_COLORS["bg"]),
            ("☀️ Светлая", "light", LIGHT_COLORS["bg"])
        ]
        
        for text, val, color in themes:
            btn = ctk.CTkRadioButton(
                theme_frame, text=text, variable=self.theme_var,
                value=val, command=self._on_theme_change
            )
            btn.pack(anchor="w", pady=2)
        
        self.preview_frame = ctk.CTkFrame(scroll, width=420, height=80, corner_radius=10)
        self.preview_frame.pack(pady=15, padx=10)
        self.preview_frame.pack_propagate(False)
        
        preview_label = ctk.CTkLabel(
            self.preview_frame, text="Предпросмотр темы",
            font=ctk.CTkFont(size=14)
        )
        preview_label.pack(expand=True)
        self._update_theme_preview()
        
        ctk.CTkLabel(
            scroll, text="📍 Позиция панели:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(15, 5))
        
        pos_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pos_frame.pack(fill="x", padx=10, pady=5)
        
        self.pos_var = tk.StringVar(value=self.settings["ui"]["panel_position"])
        positions = [
            ("Справа (по умолчанию)", "right"),
            ("Слева", "left"),
        ]
        
        for text, val in positions:
            ctk.CTkRadioButton(
                pos_frame, text=text, variable=self.pos_var,
                value=val
            ).pack(anchor="w", pady=2)
        
        ctk.CTkLabel(
            scroll, text="🎬 Скорость анимации:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(15, 5))
        
        self.anim_speed_slider = ctk.CTkSlider(
            scroll, from_=0.5, to=2.0, number_of_steps=15,
            command=self._update_anim_speed_label
        )
        self.anim_speed_slider.set(self.settings["ui"]["animation_speed"])
        self.anim_speed_slider.pack(fill="x", padx=10, pady=5)
        
        self.anim_speed_label = ctk.CTkLabel(
            scroll, text=f"{self.settings['ui']['animation_speed']}x"
        )
        self.anim_speed_label.pack(anchor="e", padx=10, pady=(0, 10))

    def _build_behavior_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, width=480, height=460)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkLabel(
            scroll, text="🔢 Максимум пространств:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(10, 5))
        
        self.max_spaces_slider = ctk.CTkSlider(
            scroll, from_=2, to=10, number_of_steps=8,
            command=self._update_max_spaces_label
        )
        self.max_spaces_slider.set(self.settings["behavior"]["max_spaces"])
        self.max_spaces_slider.pack(fill="x", padx=10, pady=5)
        
        self.max_spaces_label = ctk.CTkLabel(
            scroll, text=f"{int(self.settings['behavior']['max_spaces'])}"
        )
        self.max_spaces_label.pack(anchor="e", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(
            scroll, text="🪟 Максимум окон на пространство:",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(10, 5))
        
        self.max_windows_slider = ctk.CTkSlider(
            scroll, from_=5, to=50, number_of_steps=45,
            command=self._update_max_windows_label
        )
        self.max_windows_slider.set(self.settings["behavior"]["max_windows_per_space"])
        self.max_windows_slider.pack(fill="x", padx=10, pady=5)
        
        self.max_windows_label = ctk.CTkLabel(
            scroll, text=f"{int(self.settings['behavior']['max_windows_per_space'])}"
        )
        self.max_windows_label.pack(anchor="e", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(
            scroll, text="⏱️ Авто-закрытие панели (сек):",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(10, 5))
        
        self.auto_close_slider = ctk.CTkSlider(
            scroll, from_=0, to=60, number_of_steps=12,
            command=self._update_auto_close_label
        )
        self.auto_close_slider.set(self.settings["behavior"]["auto_close_delay"])
        self.auto_close_slider.pack(fill="x", padx=10, pady=5)
        
        auto_close_val = int(self.settings["behavior"]["auto_close_delay"])
        auto_close_text = "отключено" if auto_close_val == 0 else f"{auto_close_val} сек"
        self.auto_close_label = ctk.CTkLabel(scroll, text=auto_close_text)
        self.auto_close_label.pack(anchor="e", padx=10, pady=(0, 10))
        
        # ✅ НОВЫЙ: задержка после применения расстановки
        ctk.CTkLabel(
            scroll, text="⏱️ Задержка закрытия после применения (сек):",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(15, 5))
        
        self.auto_close_apply_slider = ctk.CTkSlider(
            scroll, from_=1, to=10, number_of_steps=9,
            command=self._update_auto_close_apply_label
        )
        self.auto_close_apply_slider.set(self.settings["behavior"]["auto_close_after_apply"])
        self.auto_close_apply_slider.pack(fill="x", padx=10, pady=5)
        
        self.auto_close_apply_label = ctk.CTkLabel(
            scroll, text=f"{int(self.settings['behavior']['auto_close_after_apply'])} сек"
        )
        self.auto_close_apply_label.pack(anchor="e", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(
            scroll, text="🔄 Интервал обновления окон (мс):",
            font=ctk.CTkFont(weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(10, 5))
        
        self.monitor_interval_slider = ctk.CTkSlider(
            scroll, from_=500, to=5000, number_of_steps=9,
            command=self._update_monitor_interval_label
        )
        self.monitor_interval_slider.set(self.settings["behavior"]["window_monitor_interval"])
        self.monitor_interval_slider.pack(fill="x", padx=10, pady=5)
        
        self.monitor_interval_label = ctk.CTkLabel(
            scroll, text=f"{int(self.settings['behavior']['window_monitor_interval'])} мс"
        )
        self.monitor_interval_label.pack(anchor="e", padx=10, pady=(0, 10))
        
        self.minimize_var = tk.BooleanVar(
            value=self.settings["behavior"]["minimize_other_spaces"]
        )
        minimize_check = ctk.CTkCheckBox(
            scroll, text="Сворачивать окна других пространств",
            variable=self.minimize_var
        )
        minimize_check.pack(anchor="w", padx=10, pady=15)

    def _build_hotkeys_tab(self, parent):
        """✅ ПОЛНОСТЬЮ РАБОЧИЙ ТАБ ГОРЯЧИХ КЛАВИШ"""
        scroll = ctk.CTkScrollableFrame(parent, width=480, height=460)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkLabel(
            scroll, text="⌨️ Настройка горячих клавиш",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=10)
        
        info_label = ctk.CTkLabel(
            scroll,
            text="💡 Нажмите на поле и введите новую комбинацию клавиш.\n"
                 "Поддерживаются: Ctrl, Alt, Shift, Win + буквы/цифры/F1-F12",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            justify="left"
        )
        info_label.pack(fill="x", padx=10, pady=10)
        
        # Словарь для хранения виджетов ввода хоткеев
        self.hotkey_entries = {}
        
        # Список хоткеев для редактирования
        hotkeys_config = [
            ("Открыть/закрыть панель", "toggle_panel", self.settings["hotkeys"]["toggle_panel"]),
            ("Применить расстановку", "apply_layout", self.settings["hotkeys"]["apply_layout"]),
            ("Сохранить позиции", "save_layout", self.settings["hotkeys"]["save_layout"]),
            ("Показать рабочий стол", "show_desktop", self.settings["hotkeys"]["show_desktop"]),
            ("Режим «Все окна»", "all_windows_mode", self.settings["hotkeys"].get("all_windows_mode", "Ctrl+A")),
        ]
        
        for desc, key_name, default_val in hotkeys_config:
            frame = ctk.CTkFrame(scroll, fg_color="transparent")
            frame.pack(fill="x", padx=10, pady=4)
            
            ctk.CTkLabel(frame, text=desc, width=220, anchor="w").pack(side="left")
            
            entry = ctk.CTkEntry(
                frame, width=140, height=32,
                placeholder_text=default_val,
                font=ctk.CTkFont(size=11)
            )
            entry.insert(0, format_hotkey_display(default_val))
            entry.pack(side="right")
            
            # Бинды для записи хоткея
            entry.bind("<FocusIn>", lambda e, k=key_name, ent=entry: self._start_recording(k, ent))
            entry.bind("<FocusOut>", lambda e, ent=entry: self._stop_recording(ent))
            entry.bind("<Key>", lambda e, k=key_name, ent=entry: self._on_hotkey_input(e, k, ent))
            
            self.hotkey_entries[key_name] = entry
        
        # Переключатели пространств (группа)
        ctk.CTkLabel(
            scroll, text="\n🔄 Переключение пространств (группа):",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=10, pady=(15, 5))
        
        for i in range(min(4, self.settings["behavior"]["max_spaces"])):
            frame = ctk.CTkFrame(scroll, fg_color="transparent")
            frame.pack(fill="x", padx=10, pady=2)
            
            ctk.CTkLabel(frame, text=f"Пространство {i+1}", width=220, anchor="w").pack(side="left")
            
            entry = ctk.CTkEntry(frame, width=140, height=32, font=ctk.CTkFont(size=11))
            default = f"Ctrl+F{i+1}"
            entry.insert(0, format_hotkey_display(default))
            entry.pack(side="right")
            
            entry.bind("<FocusIn>", lambda e, idx=i, ent=entry: self._start_recording_space(idx, ent))
            entry.bind("<FocusOut>", lambda e, ent=entry: self._stop_recording(ent))
            entry.bind("<Key>", lambda e, idx=i, ent=entry: self._on_space_hotkey_input(e, idx, ent))
            
            self.hotkey_entries[f"space_{i+1}"] = (entry, f"Ctrl+F{i+1}")

    def _start_recording(self, key_name: str, entry):
        """Начинает запись нового хоткея"""
        self._recording_hotkey = key_name
        entry.configure(placeholder_text="Нажмите комбинацию...", fg_color=WATER_COLORS["accent_glow"])
        entry.delete(0, tk.END)

    def _stop_recording(self, entry):
        """Завершает запись хоткея"""
        self._recording_hotkey = None
        entry.configure(fg_color=None)

    def _on_hotkey_input(self, event, key_name: str, entry):
        """Обрабатывает ввод хоткея"""
        if self._recording_hotkey != key_name:
            return
        
        # Игнорируем модификаторы по отдельности
        if event.keysym in ["Control", "Alt", "Shift", "Control_L", "Control_R", 
                           "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Windows_L", "Windows_R"]:
            return "break"
        
        # Собираем комбинацию
        modifiers = []
        if event.state & 0x0004:  # Control
            modifiers.append("Ctrl")
        if event.state & 0x20000:  # Alt
            modifiers.append("Alt")
        if event.state & 0x0001:  # Shift
            modifiers.append("Shift")
        if event.state & 0x0080:  # Windows key (approximation)
            modifiers.append("Win")
        
        # Основная клавиша
        key = event.keysym
        if key in ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]:
            main_key = key
        elif len(key) == 1 and key.isalpha():
            main_key = key.upper()
        elif key in ["0","1","2","3","4","5","6","7","8","9"]:
            main_key = key
        elif key == "space":
            main_key = "Space"
        elif key == "return":
            main_key = "Enter"
        elif key == "escape":
            main_key = "Esc"
        else:
            main_key = key.capitalize()
        
        # Формируем строку
        if modifiers:
            hotkey_str = '+'.join(modifiers) + '+' + main_key
        else:
            hotkey_str = main_key
        
        # Сохраняем в настройки
        self.settings["hotkeys"][key_name] = normalize_hotkey(hotkey_str)
        
        # Обновляем UI
        entry.delete(0, tk.END)
        entry.insert(0, format_hotkey_display(hotkey_str))
        entry.configure(fg_color=None)
        self._recording_hotkey = None
        
        # Предпросмотр
        if self.on_preview:
            self.on_preview({"hotkeys": {key_name: normalize_hotkey(hotkey_str)}})
        
        logger.info(f"Hotkey updated: {key_name} = {hotkey_str}")
        return "break"

    def _start_recording_space(self, idx: int, entry):
        """Запись хоткея для переключения пространства"""
        self._recording_hotkey = f"space_{idx+1}"
        entry.configure(placeholder_text="Нажмите комбинацию...", fg_color=WATER_COLORS["accent_glow"])
        entry.delete(0, tk.END)

    def _on_space_hotkey_input(self, event, idx: int, entry):
        """Обработка ввода хоткея для пространства"""
        if self._recording_hotkey != f"space_{idx+1}":
            return "break"
        
        if event.keysym in ["Control", "Alt", "Shift", "Control_L", "Control_R", 
                           "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Windows_L", "Windows_R"]:
            return "break"
        
        modifiers = []
        if event.state & 0x0004:
            modifiers.append("Ctrl")
        if event.state & 0x20000:
            modifiers.append("Alt")
        if event.state & 0x0001:
            modifiers.append("Shift")
        
        key = event.keysym
        if key.startswith("F") and key[1:].isdigit():
            main_key = key
        elif len(key) == 1 and key.isalpha():
            main_key = key.upper()
        else:
            main_key = key.capitalize()
        
        hotkey_str = '+'.join(modifiers) + '+' + main_key if modifiers else main_key
        normalized = normalize_hotkey(hotkey_str)
        
        # Обновляем список в настройках
        switch_spaces = self.settings["hotkeys"].get("switch_spaces", ["Ctrl+F1","Ctrl+F2","Ctrl+F3","Ctrl+F4"])
        while len(switch_spaces) <= idx:
            switch_spaces.append(f"Ctrl+F{len(switch_spaces)+1}")
        switch_spaces[idx] = normalized
        self.settings["hotkeys"]["switch_spaces"] = switch_spaces
        
        entry.delete(0, tk.END)
        entry.insert(0, format_hotkey_display(hotkey_str))
        entry.configure(fg_color=None)
        self._recording_hotkey = None
        
        if self.on_preview:
            self.on_preview({"hotkeys": {"switch_spaces": switch_spaces}})
        
        logger.info(f"Space hotkey updated: Space {idx+1} = {hotkey_str}")
        return "break"

    def _update_theme_preview(self):
        theme = self.theme_var.get()
        colors = {
            "water": (WATER_COLORS["bg"], WATER_COLORS["accent"], "💧 Водяная тема"),
            "dark": (DARK_COLORS["bg"], DARK_COLORS["accent"], "🌙 Тёмная тема"),
            "light": (LIGHT_COLORS["bg"], LIGHT_COLORS["accent"], "☀️ Светлая тема")
        }
        bg, accent, text = colors.get(theme, colors["water"])
        self.preview_frame.configure(fg_color=bg)
        for widget in self.preview_frame.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                widget.configure(text=f"{text}\nПредпросмотр")

    def _on_theme_change(self):
        self._update_theme_preview()
        if self.on_preview:
            self.on_preview({"ui": {"theme": self.theme_var.get()}})

    def _update_anim_speed_label(self, val):
        self.anim_speed_label.configure(text=f"{float(val):.1f}x")

    def _update_max_spaces_label(self, val):
        self.max_spaces_label.configure(text=f"{int(val)}")

    def _update_max_windows_label(self, val):
        self.max_windows_label.configure(text=f"{int(val)}")

    def _update_auto_close_label(self, val):
        val = int(val)
        text = "отключено" if val == 0 else f"{val} сек"
        self.auto_close_label.configure(text=text)

    def _update_auto_close_apply_label(self, val):
        self.auto_close_apply_label.configure(text=f"{int(val)} сек")

    def _update_monitor_interval_label(self, val):
        self.monitor_interval_label.configure(text=f"{int(val)} мс")

    def _save(self):
        """Сохраняет настройки"""
        self.settings["ui"]["theme"] = self.theme_var.get()
        self.settings["ui"]["panel_position"] = self.pos_var.get()
        self.settings["ui"]["animation_speed"] = float(self.anim_speed_slider.get())
        
        self.settings["behavior"]["max_spaces"] = int(self.max_spaces_slider.get())
        self.settings["behavior"]["max_windows_per_space"] = int(self.max_windows_slider.get())
        self.settings["behavior"]["auto_close_delay"] = int(self.auto_close_slider.get())
        self.settings["behavior"]["auto_close_after_apply"] = int(self.auto_close_apply_slider.get())  # ✅
        self.settings["behavior"]["window_monitor_interval"] = int(self.monitor_interval_slider.get())
        self.settings["behavior"]["minimize_other_spaces"] = self.minimize_var.get()
        
        # ✅ Сохраняем хоткеи из полей ввода
        for key_name, entry in self.hotkey_entries.items():
            if isinstance(entry, tuple):  # Для пространств
                entry_widget, default = entry
                val = entry_widget.get().strip()
                if val:
                    # Уже сохранено в _on_space_hotkey_input
                    pass
            else:
                val = entry.get().strip()
                if val and key_name in self.settings["hotkeys"]:
                    # Уже сохранено в _on_hotkey_input
                    pass
        
        self.on_save(self.settings)
        logger.info("Settings saved from dialog")
        self.destroy()

    def _reset(self):
        """Сброс к дефолту"""
        if messagebox.askyesno("Сброс настроек", "Вернуть все настройки к значениям по умолчанию?"):
            self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
            
            self.theme_var.set(self.settings["ui"]["theme"])
            self.pos_var.set(self.settings["ui"]["panel_position"])
            self.anim_speed_slider.set(self.settings["ui"]["animation_speed"])
            self.max_spaces_slider.set(self.settings["behavior"]["max_spaces"])
            self.max_windows_slider.set(self.settings["behavior"]["max_windows_per_space"])
            self.auto_close_slider.set(self.settings["behavior"]["auto_close_delay"])
            self.auto_close_apply_slider.set(self.settings["behavior"]["auto_close_after_apply"])
            self.monitor_interval_slider.set(self.settings["behavior"]["window_monitor_interval"])
            self.minimize_var.set(self.settings["behavior"]["minimize_other_spaces"])
            
            self._update_theme_preview()
            self._update_anim_speed_label(self.settings["ui"]["animation_speed"])
            self._update_max_spaces_label(self.settings["behavior"]["max_spaces"])
            self._update_max_windows_label(self.settings["behavior"]["max_windows_per_space"])
            self._update_auto_close_label(self.settings["behavior"]["auto_close_delay"])
            self._update_auto_close_apply_label(self.settings["behavior"]["auto_close_after_apply"])
            self._update_monitor_interval_label(self.settings["behavior"]["window_monitor_interval"])
            
            # Сброс хоткеев в UI
            for key_name, default_val in [
                ("toggle_panel", DEFAULT_SETTINGS["hotkeys"]["toggle_panel"]),
                ("apply_layout", DEFAULT_SETTINGS["hotkeys"]["apply_layout"]),
                ("save_layout", DEFAULT_SETTINGS["hotkeys"]["save_layout"]),
                ("show_desktop", DEFAULT_SETTINGS["hotkeys"]["show_desktop"]),
                ("all_windows_mode", DEFAULT_SETTINGS["hotkeys"].get("all_windows_mode", "Ctrl+A")),
            ]:
                if key_name in self.hotkey_entries:
                    entry = self.hotkey_entries[key_name]
                    if not isinstance(entry, tuple):
                        entry.delete(0, tk.END)
                        entry.insert(0, format_hotkey_display(default_val))
            
            logger.info("Settings reset to default")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class SmartDesktop(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Smart Desktop")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        self.panel_expanded = False
        self.max_spaces = 4
        self.max_windows_per_space = 15
        
        # ✅ НОВОЕ: режим "Все окна"
        self.show_all_windows_mode = False
        
        self.settings = DEFAULT_SETTINGS.copy()
        self._load_settings()
        
        self.max_spaces = self.settings["behavior"]["max_spaces"]
        self.max_windows_per_space = self.settings["behavior"]["max_windows_per_space"]
        
        self._apply_theme_settings()
        self._update_screen_metrics()
        self._position_flag()
        
        self.configure(fg_color=WATER_COLORS["bg"])
        self.attributes("-alpha", 0.99)

        self.bg_canvas = tk.Canvas(
            self, bg=WATER_COLORS["bg"],
            highlightthickness=0, bd=0
        )
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self.bg_canvas.config(doublebuffer=True)
        except:
            pass
        self.ripple_manager = RippleManager(self.bg_canvas)

        self.spaces: List[Dict] = [{"windows": []} for _ in range(self.max_spaces)]
        self.cur_space = 0
        self.available: List[Tuple[int, str]] = []
        self.card_widgets: List[ctk.CTkFrame] = []
        
        self._window_rect_cache: Dict[int, Tuple] = {}
        self._cache_timestamp = 0
        self._cache_ttl = 0.5
        
        self._window_monitor_active = False
        self._last_window_hash = None
        
        self._auto_close_timer = None
        self._ignore_auto_close_until = 0
        
        self._load_config()

        self._init_flag_button()
        self._init_header()
        self._init_content()
        self._init_status()
        self._init_hotkeys()
        
        self.after(200, self._refresh_windows_async)
        
        logger.info("=== Smart Desktop v1.2 Started ===")

    def _get_work_area(self):
        """Получает рабочую область экрана (без панели задач)"""
        try:
            # SPI_GETWORKAREA возвращает (left, top, right, bottom)
            rect = win32gui.SystemParametersInfo(win32con.SPI_GETWORKAREA, 0)
            left, top, right, bottom = rect
            return left, top, right - left, bottom - top
        except Exception as e:
            logger.warning(f"Work area fallback: {e}")
            return 0, 0, self.SW, self.SH

    def _apply_theme_settings(self):
        theme = self.settings["ui"]["theme"]
        if theme == "dark":
            new_colors = DARK_COLORS.copy()
        elif theme == "light":
            new_colors = LIGHT_COLORS.copy()
        else:
            new_colors = ORIGINAL_WATER_COLORS.copy()
        
        for key in WATER_COLORS:
            if key in new_colors:
                WATER_COLORS[key] = new_colors[key]
        
        self._refresh_theme_ui()

    def _refresh_theme_ui(self):
        self.configure(fg_color=WATER_COLORS["bg"])
        
        if not self.panel_expanded and hasattr(self, 'flag_btn'):
            self.flag_btn.configure(
                fg_color=WATER_COLORS["accent"],
                hover_color=WATER_COLORS["accent_glow"]
            )
            return
        
        if not self.panel_expanded:
            return
        
        if hasattr(self, 'header_frame'):
            self.header_frame.configure(fg_color=WATER_COLORS["surface"])
        
        if hasattr(self, 'settings_btn'):
            self.settings_btn.configure(
                fg_color=WATER_COLORS["glass"],
                hover_color=WATER_COLORS["glass_border"],
                text_color=WATER_COLORS["accent"]
            )
        
        if hasattr(self, 'close_btn'):
            self.close_btn.configure(
                fg_color="#4709f0",
                hover_color="#c0392b"
            )
        
        if hasattr(self, 'desktop_btn'):
            self.desktop_btn.configure(
                fg_color=WATER_COLORS["glass"],
                hover_color="#2a6496",
                text_color=WATER_COLORS["accent"]
            )
        
        # ✅ Обновляем кнопку "Все окна"
        if hasattr(self, 'all_windows_btn'):
            is_active = self.show_all_windows_mode
            self.all_windows_btn.configure(
                fg_color=WATER_COLORS["accent"] if is_active else WATER_COLORS["glass"],
                text_color="#000" if is_active else WATER_COLORS["accent"],
                hover_color=WATER_COLORS["glass_border"]
            )
        
        if hasattr(self, 'space_btns'):
            for i, btn in enumerate(self.space_btns):
                try:
                    btn.configure(
                        fg_color=WATER_COLORS["accent"] if i == self.cur_space and not self.show_all_windows_mode else WATER_COLORS["glass"],
                        text_color="#000" if i == self.cur_space and not self.show_all_windows_mode else WATER_COLORS["text"],
                        hover_color=WATER_COLORS["glass_border"]
                    )
                except:
                    pass
        
        if hasattr(self, 'content_frame'):
            self.content_frame.configure(fg_color=WATER_COLORS["bg"])
        if hasattr(self, 'windows_scroll'):
            self.windows_scroll.configure(fg_color="transparent")
        
        if hasattr(self, '_render_windows_list'):
            try:
                self._render_windows_list()
            except:
                pass
        
        if hasattr(self, 'status'):
            self.status.configure(text_color=WATER_COLORS["text_dim"])

    def _init_flag_button(self):
        corner_radius = 0
        pos = self.settings["ui"]["panel_position"]
        flag_x = 0 if pos == "left" else 0
        
        self.flag_btn = ctk.CTkButton(
            self, text="🪟", width=40, height=40,
            font=ctk.CTkFont(size=22), fg_color=WATER_COLORS["accent"],
            hover_color=WATER_COLORS["accent_glow"], text_color="#000",
            corner_radius=corner_radius, command=self._toggle_panel
        )
        
        self.flag_btn.place(x=flag_x, y=0)
        self._add_hover_effect(self.flag_btn, WATER_COLORS["accent"], WATER_COLORS["accent_glow"])

    def _calculate_panel_width(self):
        left_buttons = 100
        space_buttons = self.max_spaces * 58
        right_buttons = 210  # ✅ Увеличено на 40px для кнопки "Все окна"
        
        self.panel_width = left_buttons + space_buttons + right_buttons
        self.panel_width = max(self.panel_width, 420)
        
        if hasattr(self, 'SW'):
            self.panel_width = min(self.panel_width, self.SW - 100)

    def _init_header(self):
        self._calculate_panel_width()
        
        self.header_frame = ctk.CTkFrame(
            self, fg_color=WATER_COLORS["surface"],
            height=52, width=self.panel_width, corner_radius=0
        )
        
        is_left = self.settings["ui"]["panel_position"] == "left"
        
        if is_left:
            self._init_header_mirrored()
        else:
            self._init_header_normal()

    def _init_header_normal(self):
        # ⚙️ Настройки
        self.settings_btn = ctk.CTkButton(
            self.header_frame, text="⚙️", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color=WATER_COLORS["glass_border"],
            text_color=WATER_COLORS["accent"], corner_radius=8,
            font=ctk.CTkFont(size=14),
            command=self._open_settings
        )
        self.settings_btn.place(x=10, y=8)
        self._add_hover_effect(self.settings_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # >> Закрыть
        self.close_btn = ctk.CTkButton(
            self.header_frame, text=">>", width=36, height=36,
            font=ctk.CTkFont(size=16, weight="bold"), fg_color="#4709f0",
            hover_color="#c0392b", text_color="#fff",
            corner_radius=8, command=self._collapse_panel
        )
        self.close_btn.place(x=60, y=8)
        self._add_hover_effect(self.close_btn, "#4709f0", "#c0392b")
        
        # Контейнер для пространств
        spaces_width = self.panel_width - 310  # ✅ Уменьшено на 40 для новой кнопки
        self.space_buttons_container = ctk.CTkFrame(
            self.header_frame, fg_color="transparent",
            width=spaces_width, height=45
        )
        self.space_buttons_container.place(x=110, y=7)
        
        self._update_space_buttons()
        
        # Правые кнопки: 🌐 🖥️ ✓ 💾
        self.right_buttons_frame = ctk.CTkFrame(
            self.header_frame, fg_color="transparent",
            width=210, height=45  # ✅ +40px
        )
        self.right_buttons_frame.place(x=self.panel_width - 210, y=7)
        
        self._init_right_buttons()

    def _init_right_buttons(self):
        """✅ ДОБАВЛЕНА КНОПКА «🌐 Все окна»"""
        # 🌐 Все окна — НОВАЯ КНОПКА
        self.all_windows_btn = ctk.CTkButton(
            self.right_buttons_frame, text="🌐", width=40, height=38,
            fg_color=WATER_COLORS["accent"] if self.show_all_windows_mode else WATER_COLORS["glass"],
            hover_color=WATER_COLORS["glass_border"],
            text_color="#000" if self.show_all_windows_mode else WATER_COLORS["accent"],
            corner_radius=8, font=ctk.CTkFont(size=14),
            command=self._toggle_all_windows_mode
        )
        self.all_windows_btn.pack(side="right", padx=5)
        self._add_hover_effect(self.all_windows_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # 💾 Сохранить
        self.save_btn = ctk.CTkButton(
            self.right_buttons_frame, text="💾", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color=WATER_COLORS["glass_border"],
            text_color=WATER_COLORS["accent"], corner_radius=8, font=ctk.CTkFont(size=16),
            command=self._save_layout
        )
        self.save_btn.pack(side="right", padx=5)
        self._add_hover_effect(self.save_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # ✓ Применить
        self.apply_btn = ctk.CTkButton(
            self.right_buttons_frame, text="✓", width=42, height=38,
            fg_color=WATER_COLORS["accent"], hover_color=WATER_COLORS["accent_glow"],
            text_color="#000", corner_radius=8, font=ctk.CTkFont(size=18, weight="bold"),
            command=self._apply_layout
        )
        self.apply_btn.pack(side="right", padx=5)
        self._add_hover_effect(self.apply_btn, WATER_COLORS["accent"], WATER_COLORS["accent_glow"])
        
        # 🖥️ Показать рабочий стол
        self.desktop_btn = ctk.CTkButton(
            self.right_buttons_frame, text="🖥️", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color="#2a6496",
            text_color=WATER_COLORS["accent"], corner_radius=8,
            font=ctk.CTkFont(size=14),
            command=self._show_desktop
        )
        self.desktop_btn.pack(side="right", padx=5)
        self._add_hover_effect(self.desktop_btn, WATER_COLORS["glass"], "#2a6496")

    def _init_header_mirrored(self):
        """Зеркальный режим (панель слева)"""
        # Левая группа: 🌐 💾 ✓ 🖥️
        self.left_buttons_frame = ctk.CTkFrame(
            self.header_frame, fg_color="transparent",
            width=210, height=45
        )
        self.left_buttons_frame.place(x=10, y=7)
        
        # 🌐 Все окна
        self.all_windows_btn = ctk.CTkButton(
            self.left_buttons_frame, text="🌐", width=40, height=38,
            fg_color=WATER_COLORS["accent"] if self.show_all_windows_mode else WATER_COLORS["glass"],
            hover_color=WATER_COLORS["glass_border"],
            text_color="#000" if self.show_all_windows_mode else WATER_COLORS["accent"],
            corner_radius=8, font=ctk.CTkFont(size=14),
            command=self._toggle_all_windows_mode
        )
        self.all_windows_btn.pack(side="left", padx=5)
        self._add_hover_effect(self.all_windows_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # 💾 Сохранить
        self.save_btn = ctk.CTkButton(
            self.left_buttons_frame, text="💾", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color=WATER_COLORS["glass_border"],
            text_color=WATER_COLORS["accent"], corner_radius=8, font=ctk.CTkFont(size=16),
            command=self._save_layout
        )
        self.save_btn.pack(side="left", padx=5)
        self._add_hover_effect(self.save_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        # ✓ Применить
        self.apply_btn = ctk.CTkButton(
            self.left_buttons_frame, text="✓", width=42, height=38,
            fg_color=WATER_COLORS["accent"], hover_color=WATER_COLORS["accent_glow"],
            text_color="#000", corner_radius=8, font=ctk.CTkFont(size=18, weight="bold"),
            command=self._apply_layout
        )
        self.apply_btn.pack(side="left", padx=5)
        self._add_hover_effect(self.apply_btn, WATER_COLORS["accent"], WATER_COLORS["accent_glow"])
        
        # 🖥️ Рабочий стол
        self.desktop_btn = ctk.CTkButton(
            self.left_buttons_frame, text="🖥️", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color="#2a6496",
            text_color=WATER_COLORS["accent"], corner_radius=8,
            font=ctk.CTkFont(size=14),
            command=self._show_desktop
        )
        self.desktop_btn.pack(side="left", padx=5)
        self._add_hover_effect(self.desktop_btn, WATER_COLORS["glass"], "#2a6496")
        
        # Центр: кнопки пространств
        spaces_width = self.panel_width - 310
        self.space_buttons_container = ctk.CTkFrame(
            self.header_frame, fg_color="transparent",
            width=spaces_width, height=45
        )
        self.space_buttons_container.place(x=210, y=7)
        
        self._update_space_buttons()
        
        # Правая группа: ⚙️ <<
        self.settings_btn = ctk.CTkButton(
            self.header_frame, text="⚙️", width=40, height=38,
            fg_color=WATER_COLORS["glass"], hover_color=WATER_COLORS["glass_border"],
            text_color=WATER_COLORS["accent"], corner_radius=8,
            font=ctk.CTkFont(size=14),
            command=self._open_settings
        )
        self.settings_btn.place(x=self.panel_width - 100, y=8)
        self._add_hover_effect(self.settings_btn, WATER_COLORS["glass"], WATER_COLORS["glass_border"])
        
        self.close_btn = ctk.CTkButton(
            self.header_frame, text="<<", width=36, height=36,
            font=ctk.CTkFont(size=16, weight="bold"), fg_color="#4709f0",
            hover_color="#c0392b", text_color="#fff",
            corner_radius=8, command=self._collapse_panel
        )
        self.close_btn.place(x=self.panel_width - 50, y=8)
        self._add_hover_effect(self.close_btn, "#4709f0", "#c0392b")
        
        self.right_buttons_frame = None

    def _toggle_all_windows_mode(self):
        """✅ Расставляет ВСЕ окна на экране (не только из пространств!)"""
        logger.info("🌐 All Windows mode: arranging ALL windows on desktop")
        
        # ✅ СОБИРАЕМ ВСЕ ДОСТУПНЫЕ ОКНА (не только из пространств!)
        all_windows = []
        for hwnd, title in self.available:
            if win32gui.IsWindow(hwnd):
                # Ищем, есть ли окно в каком-либо пространстве
                found_space = None
                is_main = False
                saved_rect = None
                
                for space_idx, space in enumerate(self.spaces):
                    for win in space["windows"]:
                        if win["hwnd"] == hwnd:
                            found_space = space_idx
                            is_main = win.get("is_main", False)
                            saved_rect = win.get("saved_rect")
                            break
                    if found_space is not None:
                        break
                
                all_windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "space": found_space,
                    "is_main": is_main,
                    "saved_rect": saved_rect
                })
        
        if not all_windows:
            self.status.configure(text="⚠️ Нет окон для расстановки")
            self.ripple_manager.create_ripple(190, 20, is_main=False, max_radius=40)
            return
        
        logger.info(f"🌐 Found {len(all_windows)} windows to arrange")
        
        # ✅ Восстанавливаем и расставляем окна
        self._arrange_windows_grid(all_windows)
        
        # Визуальный фидбек
        self.status.configure(text=f"🌐 Расставлено: {len(all_windows)} окон")
        self.ripple_manager.create_ripple(self.panel_width // 2, 26, is_main=True, max_radius=80)
        
        # ✅ Панель закрывается через настраиваемую задержку
        apply_delay = self.settings["behavior"]["auto_close_after_apply"] * 1000
        self.after(apply_delay, self._collapse_panel)
        
        logger.info(f"Arranged {len(all_windows)} windows from all spaces")

    def _init_content(self):
        self.content_frame = ctk.CTkFrame(
            self, fg_color=WATER_COLORS["bg"],
            width=380, height=980 - 52
        )
        
        # ✅ Динамический заголовок в зависимости от режима
        def get_header_text():
            if self.show_all_windows_mode:
                return "🌐 Все окна (из всех пространств):"
            else:
                return f"🪟 Окна пространства {self.cur_space + 1} (✓ — добавить, ⭐ — главное):"
        
        ctk.CTkLabel(
            self.content_frame, text=get_header_text(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=WATER_COLORS["text_dim"], fg_color="transparent",
            width=360, height=24, anchor="w"
        ).place(x=10, y=8)
        
        self.windows_scroll = ctk.CTkScrollableFrame(
            self.content_frame, fg_color="transparent",
            width=360, height=980 - 140
        )
        self.windows_scroll.place(x=10, y=35)
        
        # Подсказка
        hotkey_frame = ctk.CTkFrame(
            self.content_frame, fg_color=WATER_COLORS["surface"],
            height=60, width=360, corner_radius=8
        )
        hotkey_frame.place(x=10, y=980 - 140)
        
        ctk.CTkLabel(
            hotkey_frame, text="⌨️ Горячие клавиши:",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=WATER_COLORS["accent"], fg_color="transparent"
        ).place(x=10, y=0)
        
        ctk.CTkLabel(
            hotkey_frame,
            text="F1 — меню  •  F2 — расставить  •  F3 — сохранить  •  Ctrl+A — все окна",
            font=ctk.CTkFont(size=9),
            text_color=WATER_COLORS["text"], fg_color="transparent"
        ).place(x=10, y=20)
        
        ctk.CTkLabel(
            hotkey_frame, text="⚙️ — настройки  •  🖥️ — рабочий стол",
            font=ctk.CTkFont(size=9),
            text_color=WATER_COLORS["text_dim"], fg_color="transparent"
        ).place(x=10, y=38)

    def _init_status(self):
        self.status = ctk.CTkLabel(
            self, text="🚀 Готов", anchor="center",
            font=ctk.CTkFont(size=9),
            text_color=WATER_COLORS["text_dim"], fg_color="transparent",
            width=380, height=20
        )
        self.status.place(x=0, y=980 - 20)

    def _init_hotkeys(self):
        """✅ Инициализация горячих клавиш с правильным форматом для Tkinter"""
        
        # Вспомогательная функция для конвертации в формат Tkinter
        def to_tk_format(key: str) -> str:
            """Конвертирует 'Ctrl+A' → '<Control-a>' для tkinter"""
            key = key.strip().lower()
            # Заменяем алиасы
            key = key.replace("ctrl", "control")
            key = key.replace("win", "windows")
            key = key.replace("cmd", "windows")
            # Убираем пробелы вокруг +
            key = re.sub(r'\s*\+\s*', '+', key)
            
            parts = key.split('+')
            tk_parts = []
            for p in parts:
                if p in ["control", "alt", "shift", "windows"]:
                    tk_parts.append(p.capitalize())
                elif p.startswith("f") and p[1:].isdigit():
                    tk_parts.append(p.upper())  # F1, F2, etc.
                elif len(p) == 1 and p.isalpha():
                    tk_parts.append(p.lower())  # a, b, c...
                else:
                    tk_parts.append(p)
            
            return '<' + '-'.join(tk_parts) + '>'
        
        # Стандартные хоткеи
        self.bind("<F1>", lambda e: self._toggle_panel())
        self.bind("<F2>", lambda e: self._apply_layout())
        self.bind("<F3>", lambda e: self._save_layout())
        self.bind("<Escape>", lambda e: self._collapse_panel())
        self.bind("<Control-d>", lambda e: self._show_desktop())
        
        # ✅ Хоткей для "Все окна" — с конвертацией в tkinter-формат
        all_windows_key = self.settings["hotkeys"].get("all_windows_mode", "Ctrl+A")
        tk_key = to_tk_format(all_windows_key)
        self.bind(tk_key, lambda e: self._toggle_all_windows_mode())
        logger.debug(f"Bound all_windows_mode: {all_windows_key} → {tk_key}")
        
        # Переключение пространств: Ctrl+F1..F4
        for i in range(min(4, self.max_spaces)):
            self.bind(f"<Control-F{i+1}>", lambda e, idx=i: self._quick_switch_space(idx))
        
        # Глобальные хоткеи (через keyboard модуль)
        if KEYBOARD_AVAILABLE:
            self._setup_global_hotkeys()

    def _setup_global_hotkeys(self):
        """Регистрация глобальных хоткеев через keyboard модуль"""
        try:
            keyboard.add_hotkey('ctrl+alt+f1', self._toggle_panel, suppress=False)
            keyboard.add_hotkey('ctrl+alt+f2', self._apply_layout, suppress=False)
            keyboard.add_hotkey('ctrl+alt+f3', self._save_layout, suppress=False)
            keyboard.add_hotkey('ctrl+alt+d', self._show_desktop, suppress=False)
            
            # ✅ Хоткей для "Все окна" — используем parse_hotkey для keyboard модуля
            all_windows_key = self.settings["hotkeys"].get("all_windows_mode", "Ctrl+A")
            if all_windows_key:
                keyboard.add_hotkey(parse_hotkey(all_windows_key), self._toggle_all_windows_mode, suppress=False)
                logger.debug(f"Global hotkey registered: {all_windows_key}")
            
            for i in range(min(4, self.max_spaces)):
                keyboard.add_hotkey(f'ctrl+f{i+1}', lambda idx=i: self._quick_switch_space(idx), suppress=False)
            
            logger.info("Global hotkeys registered")
        except Exception as e:
            logger.warning(f"Could not register global hotkeys: {e}")

    def _add_hover_effect(self, widget, base_color, hover_color):
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
            pass

    def _update_screen_metrics(self):
        try:
            user32 = ctypes.windll.user32
            self.SW = user32.GetSystemMetrics(0)
            self.SH = user32.GetSystemMetrics(1)
        except Exception as e:
            logger.error(f"Screen metrics error: {e}")
            self.SW, self.SH = 1920, 1080

    def _position_flag(self):
        self._update_screen_metrics()
        pos = self.settings["ui"]["panel_position"]
        if pos == "left":
            px = 0
        else:
            px = self.SW - 40
        py = 50
        self.geometry(f"40x40+{px}+{py}")

    def _toggle_panel(self):
        if self.panel_expanded:
            self._collapse_panel()
        else:
            self._expand_panel()

    def _expand_panel(self):
        if self.panel_expanded:
            return
        self.panel_expanded = True
        
        self._update_screen_metrics()
        self._calculate_panel_width()
        
        self.flag_btn.place_forget()
        self.header_frame.place(x=0, y=0)
        self.content_frame.place(x=0, y=52)
        
        max_height = self.SH - 100
        panel_height = min(980, max_height)
        
        pos = self.settings["ui"]["panel_position"]
        px = 0 if pos == "left" else self.SW - self.panel_width
        py = max(50, (self.SH - panel_height) // 2)
        
        self.geometry(f"{self.panel_width}x{panel_height}+{px}+{py}")
        
        self.header_frame.configure(width=self.panel_width, height=52)
        self.content_frame.configure(width=self.panel_width, height=panel_height - 52)
        
        scroll_height = panel_height - 140
        self.windows_scroll.configure(height=max(200, scroll_height), width=self.panel_width - 20)
        self.windows_scroll.place(x=10, y=35)
        
        hotkey_y = panel_height - 140
        for widget in self.content_frame.winfo_children():
            if isinstance(widget, ctk.CTkFrame) and widget.winfo_y() > 980 - 200:
                widget.configure(width=self.panel_width - 20)
                widget.place(y=hotkey_y, x=10)
        
        self.status.configure(width=self.panel_width)
        self.status.place(y=panel_height - 20)
        
        self._animate_alpha(0.0, 0.99, duration=200)
        
        self._refresh_windows_async()
        self._start_window_monitor()
        self._reset_auto_close_timer()
        
        self.ripple_manager.create_ripple(self.panel_width // 2, 20, is_main=True, max_radius=60)
        logger.info("Panel expanded")

    def _collapse_panel(self):
        if not self.panel_expanded:
            return
        self._stop_window_monitor()
        if self._auto_close_timer:
            self.after_cancel(self._auto_close_timer)
            self._auto_close_timer = None
        self._animate_alpha(0.99, 0.0, duration=150, on_complete=self._finish_collapse)
        logger.info("Panel collapsing")

    def _animate_alpha(self, start, end, duration, on_complete=None):
        steps = 10
        delay = max(10, duration // steps)
        delta = (end - start) / steps
        current = [start]
        
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
        self.panel_expanded = False
        self.header_frame.place_forget()
        self.content_frame.place_forget()
        self.flag_btn.place(x=0, y=0)
        self._position_flag()
        self.attributes("-alpha", 0.99)
        logger.info("Panel collapsed")

    def _switch_space(self, idx):
        """Переключает пространство с правильной очисткой экрана"""
        if idx >= len(self.spaces):
            return
        if self.cur_space == idx:
            return
        
        # ✅ Выход из режима "Все окна" при переключении пространства
        if self.show_all_windows_mode:
            self.show_all_windows_mode = False
            if hasattr(self, 'all_windows_btn'):
                self.all_windows_btn.configure(
                    fg_color=WATER_COLORS["glass"],
                    text_color=WATER_COLORS["accent"]
                )
        
        # ✅ СВЁРТЫВАЕМ ОКНА ДРУГИХ ПРОСТРАНСТВ (если включена настройка)
        if self.settings["behavior"]["minimize_other_spaces"]:
            for i, sp in enumerate(self.spaces):
                if i == idx:  # Не сворачиваем окна целевого пространства
                    continue
                for win in sp["windows"]:
                    try:
                        if win32gui.IsWindowVisible(win["hwnd"]):
                            win32gui.ShowWindow(win["hwnd"], win32con.SW_MINIMIZE)
                    except Exception as e:
                        logger.debug(f"Minimize error in switch_space: {e}")
            time.sleep(0.01)  # Микро-пауза для стабильности
        
        # Переключаем пространство
        self.cur_space = idx
        for i, btn in enumerate(self.space_btns):
            btn.configure(
                fg_color=WATER_COLORS["accent"] if i == idx else WATER_COLORS["glass"],
                text_color="#000" if i == idx else WATER_COLORS["text"]
            )
        self._render_windows_list()
        self.ripple_manager.create_ripple(110 + idx * 52, 20, is_main=False, max_radius=40)
        
        self._on_activity()
        self._ignore_auto_close_until = time.time() + 3
        logger.info(f"Switched to space {idx + 1} (other spaces minimized)")

    def _quick_switch_space(self, idx):
        if idx >= len(self.spaces):
            return
        if self.cur_space == idx and not self.show_all_windows_mode:
            if idx < len(self.space_btns):
                btn = self.space_btns[idx]
                orig = btn.cget("fg_color")
                btn.configure(fg_color=WATER_COLORS["accent_glow"])
                self.after(100, lambda: btn.configure(fg_color=orig))
            return
        
        if self.show_all_windows_mode:
            self.show_all_windows_mode = False
            if hasattr(self, 'all_windows_btn'):
                self.all_windows_btn.configure(
                    fg_color=WATER_COLORS["glass"],
                    text_color=WATER_COLORS["accent"]
                )
        
        if self.panel_expanded:
            self.ripple_manager.create_ripple(110 + idx * 52, 20, is_main=True, max_radius=30)
        
        self._switch_space(idx)
        
        if not self.panel_expanded:
            self.status.configure(text=f"🌍 Пространство {idx + 1}")
            self.after(2000, lambda: self.status.configure(text=""))

    # ========================================================================
    # REAL-TIME WINDOW MONITORING
    # ========================================================================

    def _start_window_monitor(self):
        if self._window_monitor_active:
            return
        self._window_monitor_active = True
        self._last_window_hash = None
        self._check_windows_changed()
        logger.info("Window monitor started")

    def _stop_window_monitor(self):
        self._window_monitor_active = False
        logger.info("Window monitor stopped")

    def _check_windows_changed(self):
        if not self._window_monitor_active or not self.panel_expanded:
            self.after(self.settings["behavior"]["window_monitor_interval"], self._check_windows_changed)
            return
        try:
            current_hash = hash(tuple(sorted(
                (hwnd, win32gui.GetWindowText(hwnd)[:20])
                for hwnd, _ in self.available[:20]
            )))
            if current_hash != self._last_window_hash:
                self._last_window_hash = current_hash
                self._refresh_windows_async()
            else:
                self.after(self.settings["behavior"]["window_monitor_interval"], self._check_windows_changed)
        except Exception as e:
            logger.debug(f"Window check error: {e}")
            self.after(self.settings["behavior"]["window_monitor_interval"], self._check_windows_changed)

    # ========================================================================
    # AUTO-CLOSE PANEL — ИСПРАВЛЕННЫЙ ТАЙМЕР
    # ========================================================================

    def _reset_auto_close_timer(self, ignore_seconds=0):
        if self._auto_close_timer:
            self.after_cancel(self._auto_close_timer)
            self._auto_close_timer = None
        if ignore_seconds > 0:
            self._ignore_auto_close_until = time.time() + ignore_seconds
        delay = self.settings["behavior"]["auto_close_delay"] * 1000
        if delay <= 0:
            return
        self._auto_close_timer = self.after(delay, self._try_auto_close)

    def _try_auto_close(self):
        if time.time() < self._ignore_auto_close_until:
            self._reset_auto_close_timer()
            return
        if self.panel_expanded:
            self._collapse_panel()
            logger.info("Panel auto-closed after inactivity")

    def _on_activity(self):
        if self.panel_expanded:
            self._reset_auto_close_timer()

    # ========================================================================
    # WINDOW MANAGEMENT
    # ========================================================================

    def _refresh_windows_async(self):
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
            self.after(0, lambda: self._update_available_windows(result))
        threading.Thread(target=worker, daemon=True).start()

    def _update_available_windows(self, windows_list):
        self.available = windows_list
        if self.panel_expanded:
            self._render_windows_list()
        self.status.configure(text=f"🔍 Найдено: {len(windows_list)}")

    def _show_desktop(self):
        try:
            hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
            if hwnd:
                win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 419, 0)
            self.status.configure(text="🖥️ Рабочий стол")
            self.ripple_manager.create_ripple(190, 20, is_main=True, max_radius=60)
            logger.info("Show desktop triggered")
        except Exception as e:
            logger.error(f"Show desktop error: {e}")
            def enum_minimize(hwnd, _):
                try:
                    if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                except:
                    pass
                return True
            win32gui.EnumWindows(enum_minimize, None)

    def _restore_windows(self):
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
        """✅ ПОДДЕРЖКА РЕЖИМА «ВСЕ ОКНА» — ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        for w in self.windows_scroll.winfo_children():
            w.destroy()
        self.card_widgets = []
        
        # ✅ Определяем, какие окна показывать
        if self.show_all_windows_mode:
            # Собираем окна из ВСЕХ пространств
            all_space_hwnds = {}
            for space_idx, sp in enumerate(self.spaces):
                for w in sp["windows"]:
                    all_space_hwnds[w["hwnd"]] = {"space": space_idx, "data": w}
            
            windows_to_render = []
            for hwnd, title in self.available:
                in_any_space = hwnd in all_space_hwnds
                space_info = all_space_hwnds.get(hwnd)
                is_main = space_info["data"].get("is_main", False) if space_info else False
                windows_to_render.append((hwnd, title, in_any_space, is_main, space_info["space"] if space_info else None))
            
            # Для совместимости: в режиме "все окна" current_space = None
            current_space = None
            space_hwnds = set()
        else:
            # Обычный режим — только текущее пространство
            current_space = self.spaces[self.cur_space]  # ✅ ЕДИНОЕ ИМЯ
            space_hwnds = {w["hwnd"] for w in current_space["windows"]}
            windows_to_render = []
            for hwnd, title in self.available:
                in_space = hwnd in space_hwnds
                win_data = next((w for w in current_space["windows"] if w["hwnd"] == hwnd), None)
                is_main = win_data.get("is_main", False) if win_data else False
                windows_to_render.append((hwnd, title, in_space, is_main, None))
        
        row_width = self.panel_width - 20 if self.panel_expanded else 360
        
        for item in windows_to_render:
            hwnd, title, in_space, is_main, space_idx = item
            bg_color = WATER_COLORS["glass"] if in_space else WATER_COLORS["surface"]
            
            row = ctk.CTkFrame(
                self.windows_scroll, fg_color=bg_color,
                corner_radius=8, height=44, width=row_width
            )
            row.pack(fill=tk.X, pady=2, padx=0)
            row.pack_propagate(False)
            
            # ✅ Показываем номер пространства в режиме "Все окна"
            if self.show_all_windows_mode and space_idx is not None:
                display = f"[{space_idx+1}] {title}"
                if len(display) > 35:
                    display = display[:32] + "..."
            else:
                display = title if len(title) <= 35 else title[:32] + "..."
            
            label = ctk.CTkLabel(
                row, text=display, anchor="w",
                font=ctk.CTkFont(size=10, weight="bold" if in_space else "normal"),
                text_color=WATER_COLORS["accent"] if in_space else WATER_COLORS["text"],
                width=row_width - 90, height=44
            )
            label.place(x=10, y=0)
            
            check_text = "✓" if in_space else "🟦"
            check_color = WATER_COLORS["accent"] if in_space else WATER_COLORS["text_dim"]
            
            btn_check = ctk.CTkButton(
                row, text=check_text, width=38, height=36,
                fg_color="transparent", hover_color=WATER_COLORS["glass"],
                text_color=check_color, corner_radius=6,
                font=ctk.CTkFont(size=16, weight="bold"),
                command=lambda h=hwnd, t=title, sp=space_idx: self._toggle_in_space(h, t, sp)
            )
            btn_check.place(x=row_width - 78, y=4)
            self._add_hover_effect(btn_check, "transparent", WATER_COLORS["glass"])
            
            for widget in [btn_check, label, row]:
                try:
                    widget.bind("<Button-1>", lambda e: self._on_activity())
                    widget.bind("<Enter>", lambda e: self._on_activity())
                except:
                    pass
            
            # ✅ Звезда: используем current_space вместо space
            if in_space and (not self.show_all_windows_mode or space_idx is not None):
                main_text = "⭐" if is_main else "☆"
                btn_main = ctk.CTkButton(
                    row, text=main_text, width=34, height=36,
                    fg_color="transparent", hover_color=WATER_COLORS["glass_border"],
                    text_color=WATER_COLORS["accent"] if is_main else WATER_COLORS["text_dim"],
                    corner_radius=6, font=ctk.CTkFont(size=13),
                    command=lambda h=hwnd: self._toggle_main(h)
                )
                btn_main.place(x=row_width - 36, y=4)
                self._add_hover_effect(btn_main, "transparent", WATER_COLORS["glass_border"])
                for widget in [btn_main]:
                    try:
                        widget.bind("<Button-1>", lambda e: self._on_activity())
                        widget.bind("<Enter>", lambda e: self._on_activity())
                    except:
                        pass  # ✅ отступ исправлен!
            
            self.card_widgets.append(row)

    def _toggle_in_space(self, hwnd, title, space_idx=None):
        """✅ Поддержка space_idx для режима «Все окна»"""
        # Если space_idx не указан — используем текущее пространство
        target_space = space_idx if space_idx is not None else self.cur_space
        
        if target_space >= len(self.spaces):
            return
        
        space = self.spaces[target_space]
        space_hwnds = [w["hwnd"] for w in space["windows"]]
        
        if hwnd in space_hwnds:
            space["windows"] = [w for w in space["windows"] if w["hwnd"] != hwnd]
            logger.info(f"Removed from space {target_space+1}: {title}")
        else:
            if len(space["windows"]) >= self.max_windows_per_space:
                messagebox.showwarning(
                    "Лимит",
                    f"Максимум {self.max_windows_per_space} окон на пространство!"
                )
                return
            space["windows"].append({
                "hwnd": hwnd,
                "title": title,
                "is_main": False,
                "saved_rect": None
            })
            logger.info(f"Added to space {target_space+1}: {title}")
        
        self._save_config()
        self._render_windows_list()

    def _toggle_main(self, hwnd):
        # ✅ Используем current_space через self.cur_space
        current_space = self.spaces[self.cur_space]
        for win in current_space["windows"]:  # ✅ было space["windows"]
            if win["hwnd"] == hwnd:
                win["is_main"] = not win["is_main"]
                logger.info(f"Main flag toggled: {win['title']} = {win['is_main']}")
                break
        self._save_config()
        self._render_windows_list()

    def _get_window_rect_cached(self, hwnd):
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
            self.ripple_manager.create_ripple(190, 20, is_main=True, max_radius=60)
            self._render_windows_list()
            logger.info(f"Saved positions for {saved} windows")
        else:
            messagebox.showinfo("Инфо", "Нет окон для сохранения!")
            logger.warning("Save layout: no windows to save")

    def _save_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                backup = CONFIG_FILE + ".bak"
                with open(CONFIG_FILE, "r", encoding="utf-8") as src:
                    with open(backup, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
            
            data = []
            for space in self.spaces:
                space_data = []
                for win in space["windows"]:
                    if not win32gui.IsWindow(win["hwnd"]):
                        logger.warning(f"Window no longer exists: {win['title']}")
                        continue
                    win_copy = win.copy()
                    if win_copy.get("saved_rect"):
                        win_copy["saved_rect"] = list(win_copy["saved_rect"])
                    space_data.append(win_copy)
                data.append({"windows": space_data})
            
            temp_file = CONFIG_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, CONFIG_FILE)
            logger.info(f"Config saved: {sum(len(s['windows']) for s in data)} windows")
        except Exception as e:
            logger.error(f"Config save failed: {e}", exc_info=True)
            if os.path.exists(CONFIG_FILE + ".bak"):
                try:
                    os.replace(CONFIG_FILE + ".bak", CONFIG_FILE)
                    logger.warning("Config restored from backup")
                except Exception as restore_err:
                    logger.error(f"Backup restore failed: {restore_err}")

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            logger.info("No config file found, starting fresh")
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for i, space_data in enumerate(data[:self.max_spaces]):
                for win in space_data.get("windows", []):
                    if win.get("saved_rect"):
                        win["saved_rect"] = tuple(win["saved_rect"])
                    if win32gui.IsWindow(win["hwnd"]):
                        self.spaces[i]["windows"].append(win)
                    else:
                        logger.warning(f"Skipping stale window: {win.get('title', 'unknown')}")
            logger.info(f"Config loaded: {sum(len(s['windows']) for s in self.spaces)} windows")
        except Exception as e:
            logger.error(f"Config load failed: {e}", exc_info=True)

    def _apply_layout(self):
        """Применяет расстановку окон текущего пространства"""
        space = self.spaces[self.cur_space]
        if not space["windows"]:
            messagebox.showinfo("Инфо", "Добавьте окна галочкой ✓")
            return
        
        logger.info(f"Applying layout for space {self.cur_space + 1}")
        
        if self.settings["behavior"]["minimize_other_spaces"]:
            for i, sp in enumerate(self.spaces):
                if i == self.cur_space: continue
                for win in sp["windows"]:
                    try:
                        if win32gui.IsWindowVisible(win["hwnd"]):
                            win32gui.ShowWindow(win["hwnd"], win32con.SW_MINIMIZE)
                    except: pass
        
        time.sleep(0.03)
        for win in space["windows"]:
            try: win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
            except: pass
        
        work_left, work_top, work_right, work_bottom = self._get_work_area()
        work_width = work_right - work_left
        work_height = work_bottom - work_top
        gap = 12
        MIN_W, MIN_H = 200, 150
        
        def move_window(hwnd, x, y, w, h):
            try:
                if not win32gui.IsWindow(hwnd): return
                w = max(w, MIN_W)
                h = max(h, MIN_H)
                abs_x = work_left + int(x)
                abs_y = work_top + int(y)
                abs_x = max(work_left, min(abs_x, work_right - w))
                abs_y = max(work_top, min(abs_y, work_bottom - h))
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.005)
                win32gui.MoveWindow(hwnd, abs_x, abs_y, int(w), int(h), True)
            except Exception as e:
                logger.error(f"MoveWindow failed: {e}")

        saved = [w for w in space["windows"] if w.get("saved_rect")]
        auto = [w for w in space["windows"] if not w.get("saved_rect")]
        
        for win in saved:
            x, y, w, h = win["saved_rect"]
            move_window(win["hwnd"], x, y, w, h)
            
        n = len(auto)
        main_win = next((w for w in auto if w.get("is_main")), None)
        regular_wins = [w for w in auto if not w.get("is_main")]
        
        if n == 0: pass
        elif n == 1:
            move_window(auto[0]["hwnd"], gap, gap, work_width - gap*2, work_height - gap*2)
        elif n == 2:
            if main_win:
                mw = int(work_width * 0.65)
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                move_window(regular_wins[0]["hwnd"] if regular_wins else auto[1]["hwnd"], mw, gap, work_width - mw - gap*2, work_height - gap*2)
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
                if len(regular_wins) >= 1: move_window(regular_wins[0]["hwnd"], mw, gap, rw, rh)
                if len(regular_wins) >= 2: move_window(regular_wins[1]["hwnd"], mw, gap + rh + gap, rw, rh)
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
                    if i == 0: move_window(win["hwnd"], mw, gap, rw, rh)
                    elif i == 1: move_window(win["hwnd"], mw + gap + rw, gap, rw, rh)
                    elif i == 2: move_window(win["hwnd"], mw + gap, gap + rh + gap, rw * 2 + gap, rh)
            else:
                w = (work_width - gap * 3) // 2
                h = (work_height - gap * 3) // 2
                coords = [(gap, gap, w, h), (gap+w+gap, gap, w, h),
                          (gap, gap+h+gap, w, h), (gap+w+gap, gap+h+gap, w, h)]
                for i, win in enumerate(auto): move_window(win["hwnd"], *coords[i])
        elif n >= 5:
            if main_win:
                mw = int(work_width * 0.60)
                move_window(main_win["hwnd"], gap, gap, mw - gap*2, work_height - gap*2)
                rw = work_width - mw - gap * 2
                rh = work_height - gap * 2
                cols, rows = 2, math.ceil(len(regular_wins) / 2)
                cell_w = (rw - gap * (cols + 1)) // cols
                cell_h = (rh - gap * (rows + 1)) // rows
                for i, win in enumerate(regular_wins):
                    r, c = divmod(i, cols)
                    move_window(win["hwnd"], mw + gap + c*(cell_w+gap), gap + r*(cell_h+gap), cell_w, cell_h)
            else:
                cols, rows = 3, math.ceil(n / 3)
                cell_w = (work_width - gap * (cols + 1)) // cols
                cell_h = (work_height - gap * (rows + 1)) // rows
                for i, win in enumerate(auto):
                    r, c = divmod(i, cols)
                    move_window(win["hwnd"], gap + c*(cell_w+gap), gap + r*(cell_h+gap), cell_w, cell_h)

        self.status.configure(text=f"✅ Расставлено: {len(space['windows'])}")
        self.ripple_manager.create_ripple(190, 20, is_main=True, max_radius=60)
        
        apply_delay = self.settings["behavior"]["auto_close_after_apply"] * 1000
        self.after(apply_delay, self._collapse_panel)
        logger.info(f"Layout applied: {len(space['windows'])} windows")

    def _arrange_windows_grid(self, windows_list: List[Dict]):
        """✅ Расставляет окна в РАБОЧЕЙ ОБЛАСТИ начиная с ВЕРХУ"""
        if not windows_list:
            return

        # ✅ Получаем рабочую область (без панели задач)
        screen_left, screen_top, screen_width, screen_height = self._get_work_area()
        
        gap = 8
        MIN_W, MIN_H = 200, 150
        
        def move_window(hwnd, x, y, w, h):
            try:
                if not win32gui.IsWindow(hwnd): return
                w = max(w, MIN_W)
                h = max(h, MIN_H)
                abs_x = screen_left + int(x)
                abs_y = screen_top + int(y)  # ✅ Начинаем ОТ ВЕРХА рабочей области!
                # Ограничиваем в пределах рабочей области
                abs_x = max(screen_left, min(abs_x, screen_left + screen_width - w))
                abs_y = max(screen_top, min(abs_y, screen_top + screen_height - h))
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.002)
                win32gui.MoveWindow(hwnd, abs_x, abs_y, int(w), int(h), True)
            except Exception as e:
                logger.error(f"MoveWindow failed: {e}")
        
        # Восстанавливаем все окна
        for win in windows_list:
            try: win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
            except: pass
        time.sleep(0.02)
        
        n = len(windows_list)
        
        # ✅ ОПТИМАЛЬНЫЙ РАСЧЁТ СЕТКИ
        if n == 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = 2, 1
        elif n == 3:
            cols, rows = 3, 1
        elif n == 4:
            cols, rows = 2, 2
        elif n <= 6:
            cols, rows = 3, 2
        elif n <= 9:
            cols, rows = 3, 3
        elif n <= 12:
            cols, rows = 4, 3
        else:
            cols = math.ceil(math.sqrt(n * 1.6))
            rows = math.ceil(n / cols)
        
        # ✅ Рассчитываем размер ячейки
        available_width = screen_width - gap * (cols + 1)
        available_height = screen_height - gap * (rows + 1)
        
        cell_width = max(MIN_W, available_width // cols)
        cell_height = max(MIN_H, available_height // rows)
        
        logger.info(f"🌐 Grid: {n} windows → {cols}×{rows}, cell: {cell_width}×{cell_height}")
        
        # ✅ Расставляем окна ПОРЯДКОВО: слева-направо, сверху-вниз
        for i, win in enumerate(windows_list):
            row = i // cols
            col = i % cols
            
            x = gap + col * (cell_width + gap)
            y = gap + row * (cell_height + gap)  # ✅ y=0 — это ВЕРХ рабочей области!
            
            move_window(win["hwnd"], x, y, cell_width, cell_height)
                
        logger.info(f"🌐 Grid arranged from TOP: {n} windows in {cols}×{rows}")
        
        def move_window(hwnd, x, y, w, h):
            try:
                if not win32gui.IsWindow(hwnd): return
                w = max(w, MIN_W)
                h = max(h, MIN_H)
                abs_x = screen_left + int(x)
                abs_y = screen_top + int(y)
                # Ограничиваем в пределах экрана
                abs_x = max(screen_left, min(abs_x, screen_left + screen_width - w))
                abs_y = max(screen_top, min(abs_y, screen_top + screen_height - h))
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.002)
                win32gui.MoveWindow(hwnd, abs_x, abs_y, int(w), int(h), True)
            except Exception as e:
                logger.error(f"MoveWindow failed: {e}")
        
        # Восстанавливаем все окна
        for win in windows_list:
            try: win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
            except: pass
        time.sleep(0.02)
        
        n = len(windows_list)
        
        # ✅ ОПТИМАЛЬНЫЙ РАСЧЁТ СЕТКИ
        if n == 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = 2, 1
        elif n == 3:
            cols, rows = 3, 1
        elif n == 4:
            cols, rows = 2, 2
        elif n <= 6:
            cols, rows = 3, 2
        elif n <= 9:
            cols, rows = 3, 3
        elif n <= 12:
            cols, rows = 4, 3
        else:
            cols = math.ceil(math.sqrt(n * 1.6))
            rows = math.ceil(n / cols)
        
        # ✅ Рассчитываем размер ячейки
        available_width = screen_width - gap * (cols + 1)
        available_height = screen_height - gap * (rows + 1)
        
        cell_width = available_width // cols
        cell_height = available_height // rows
        
        logger.info(f"🌐 Grid: {n} windows → {cols}×{rows}, cell: {cell_width}×{cell_height}")
        
        # ✅ Расставляем окна ПОРЯДКОВО: слева-направо, сверху-вниз
        for i, win in enumerate(windows_list):
            row = i // cols
            col = i % cols
            
            x = gap + col * (cell_width + gap)
            y = gap + row * (cell_height + gap)  # ✅ Начинаем с y=gap (сверху!)
            
            move_window(win["hwnd"], x, y, cell_width, cell_height)
                
        logger.info(f"🌐 Full-screen grid arranged: {n} windows in {cols}×{rows} (STARTING FROM TOP)")
        
        def move_window(hwnd, x, y, w, h):
            try:
                if not win32gui.IsWindow(hwnd): return
                w = max(w, MIN_W)
                h = max(h, MIN_H)
                abs_x = screen_left + int(x)
                abs_y = screen_top + int(y)
                # Ограничиваем в пределах экрана
                abs_x = max(screen_left, min(abs_x, screen_left + screen_width - w))
                abs_y = max(screen_top, min(abs_y, screen_top + screen_height - h))
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.002)
                win32gui.MoveWindow(hwnd, abs_x, abs_y, int(w), int(h), True)
            except Exception as e:
                logger.error(f"MoveWindow failed: {e}")
        
        # Восстанавливаем все окна
        for win in windows_list:
            try: win32gui.ShowWindow(win["hwnd"], win32con.SW_RESTORE)
            except: pass
        time.sleep(0.02)
        
        n = len(windows_list)
        
        # ✅ ОПТИМАЛЬНЫЙ РАСЧЁТ СЕТКИ
        # Подбираем cols × rows так, чтобы было максимально близко к квадрату
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        
        # ✅ Корректировка: если окон мало, делаем 1 или 2 ряда
        if n == 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = 2, 1  # ✅ Горизонтально в один ряд!
        elif n == 3:
            cols, rows = 3, 1  # ✅ Три в ряд
        elif n == 4:
            cols, rows = 2, 2  # ✅ 2×2 квадрат
        elif n <= 6:
            cols, rows = 3, 2  # ✅ 3×2
        elif n <= 9:
            cols, rows = 3, 3  # ✅ 3×3
        elif n <= 12:
            cols, rows = 4, 3  # ✅ 4×3
        else:
            # Для большого количества окон
            cols = math.ceil(math.sqrt(n * 1.6))  # ✅ Шире чем выше
            rows = math.ceil(n / cols)
        
        # ✅ Рассчитываем размер ячейки
        available_width = screen_width - gap * (cols + 1)
        available_height = screen_height - gap * (rows + 1)
        
        cell_width = available_width // cols
        cell_height = available_height // rows
        
        logger.info(f"🌐 Grid: {n} windows → {cols}×{rows}, cell: {cell_width}×{cell_height}")
        
        # ✅ Расставляем окна по порядку
        for i, win in enumerate(windows_list):
            row = i // cols
            col = i % cols
            
            x = gap + col * (cell_width + gap)
            y = gap + row * (cell_height + gap)
            
            move_window(win["hwnd"], x, y, cell_width, cell_height)
                
        logger.info(f"🌐 Full-screen grid arranged: {n} windows in {cols}×{rows}")
        


    # ========================================================================
    # SETTINGS MANAGEMENT
    # ========================================================================

    def _open_settings(self):
        dialog = SettingsDialog(
            self, self.settings,
            self._apply_settings,
            self._preview_settings
        )
        dialog.wait_window()

    def _preview_settings(self, partial_settings):
        if "ui" in partial_settings and "theme" in partial_settings["ui"]:
            self._apply_theme_settings()
        if "hotkeys" in partial_settings and KEYBOARD_AVAILABLE:
            self._setup_global_hotkeys()

    def _apply_settings(self, new_settings):
        old_position = self.settings["ui"]["panel_position"]
        old_theme = self.settings["ui"]["theme"]
        
        self.settings = new_settings
        self._apply_theme_settings()
        
        self.max_spaces = self.settings["behavior"]["max_spaces"]
        self.max_windows_per_space = self.settings["behavior"]["max_windows_per_space"]
        
        while len(self.spaces) < self.max_spaces:
            self.spaces.append({"windows": []})
        if len(self.spaces) > self.max_spaces:
            self.spaces = self.spaces[:self.max_spaces]
        
        if old_position != self.settings["ui"]["panel_position"] or old_theme != self.settings["ui"]["theme"]:
            if self.panel_expanded:
                self.header_frame.place_forget()
                self._calculate_panel_width()
                self._init_header()
                self.header_frame.place(x=0, y=0)
                self.content_frame.place(x=0, y=52)
                self.content_frame.configure(width=self.panel_width, height=self.winfo_height() - 52)
                self.windows_scroll.configure(width=self.panel_width - 20)
                for widget in self.content_frame.winfo_children():
                    if isinstance(widget, ctk.CTkFrame) and widget.winfo_y() > self.winfo_height() - 200:
                        widget.configure(width=self.panel_width - 20)
                self.status.configure(width=self.panel_width)
                self.geometry(f"{self.panel_width}x{self.winfo_height()}+{self.winfo_x()}+{self.winfo_y()}")
                self._render_windows_list()
            else:
                self._calculate_panel_width()
        else:
            if self.panel_expanded:
                self.header_frame.configure(width=self.panel_width, height=52)
                self._update_space_buttons()
                if hasattr(self, 'right_buttons_frame') and self.right_buttons_frame:
                    self.right_buttons_frame.place(x=self.panel_width - 210, y=7)
                self.content_frame.configure(width=self.panel_width)
                self.windows_scroll.configure(width=self.panel_width - 20)
                self.status.configure(width=self.panel_width)
                self.geometry(f"{self.panel_width}x{self.winfo_height()}+{self.winfo_x()}+{self.winfo_y()}")
        
        if self._window_monitor_active:
            self._stop_window_monitor()
            if self.panel_expanded:
                self._start_window_monitor()
        
        # ✅ Перерегистрируем глобальные хоткеи
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
                self._setup_global_hotkeys()
            except:
                pass
        
        self._save_settings_file()
        self.status.configure(text="⚙️ Настройки применены")
        
        if self.panel_expanded:
            self.after(500, self._collapse_panel)
        
        logger.info(f"Settings applied: position={self.settings['ui']['panel_position']}, theme={self.settings['ui']['theme']}")

    def _update_space_buttons(self):
        if hasattr(self, 'space_buttons_container'):
            for btn in self.space_buttons_container.winfo_children():
                btn.destroy()
        self.space_btns = []
        
        planet_icons = ["🌍"] * 10
        
        for i in range(min(self.max_spaces, 10)):
            btn = ctk.CTkButton(
                self.space_buttons_container, 
                text=f"{planet_icons[i]} {i+1}", 
                width=45, height=38,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=WATER_COLORS["accent"] if i == self.cur_space and not self.show_all_windows_mode else WATER_COLORS["glass"],
                hover_color=WATER_COLORS["glass_border"],
                text_color="#000" if i == self.cur_space and not self.show_all_windows_mode else WATER_COLORS["text"],
                corner_radius=8, 
                command=lambda idx=i: self._switch_space(idx)
            )
            btn.pack(side="left", padx=4)
            self.space_btns.append(btn)
            self._add_hover_effect(
                btn,
                WATER_COLORS["accent"] if i == self.cur_space else WATER_COLORS["glass"],
                WATER_COLORS["glass_border"]
            )

    def _update_panel_position(self):
        if self.panel_expanded:
            self._update_screen_metrics()
            self._calculate_panel_width()
            pos = self.settings["ui"]["panel_position"]
            px = 0 if pos == "left" else self.SW - self.panel_width
            current_geo = self.geometry()
            parts = current_geo.split('+')
            if len(parts) == 3:
                _, height, _ = parts
                self.geometry(f"{self.panel_width}x{height}+{px}+{parts[2]}")
                self.header_frame.configure(width=self.panel_width)
                self.content_frame.configure(width=self.panel_width)
                self.status.configure(width=self.panel_width)

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            logger.info("No settings file found, using defaults")
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.settings = {**DEFAULT_SETTINGS, **loaded}
            # ✅ Миграция: добавляем новые поля если их нет
            if "auto_close_after_apply" not in self.settings["behavior"]:
                self.settings["behavior"]["auto_close_after_apply"] = 3
            if "all_windows_mode" not in self.settings["hotkeys"]:
                self.settings["hotkeys"]["all_windows_mode"] = "Ctrl+A"
            logger.info("Settings loaded")
        except Exception as e:
            logger.error(f"Settings load error: {e}")
            self.settings = DEFAULT_SETTINGS.copy()

    def _save_settings_file(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            logger.info("Settings saved to file")
        except Exception as e:
            logger.error(f"Settings save error: {e}")

    def destroy(self):
        logger.info("=== Smart Desktop Shutting Down ===")
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except:
                pass
        self.ripple_manager.cleanup()
        self._save_config()
        self._save_settings_file()
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
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    logger.info("=== Smart Desktop v1.2 Starting ===")
    app = SmartDesktop()
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
    finally:
        logger.info("=== Smart Desktop Exited ===")