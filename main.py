import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as messagebox
import threading
import json
import os
import urllib.parse
import re
import webbrowser
import base64
import time
from io import BytesIO
from PIL import ImageGrab, Image
from anki import AnkiClient
from services import GeminiClient, TTSProvider, ImageProvider

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

SETTINGS_FILE = "settings.json"

class MAnkiClient(ctk.CTk):
    # ==========================================
    # CONSTANTS
    # ==========================================
    GOOGLE_LANGS = "en-US,en-GB,en-AU,en-IN,ru-RU,es-ES,es-MX,fr-FR,fr-CA,de-DE,it-IT,pt-PT,pt-BR,ja-JP,ko-KR,zh-CN,zh-TW,ar-SA,hi-IN,nl-NL,pl-PL,tr-TR,uk-UA,vi-VN,th-TH,id-ID,sv-SE,da-DK,fi-FI,no-NO,cs-CZ,el-GR,hu-HU,ro-RO,sk-SK,af,sq,am,hy,az,eu,be,bn,bs,bg,ca,ceb,ny,co,hr,eo,et,tl,fy,gl,ka,gu,ht,ha,haw,iw,hmn,is,ig,ga,jw,kn,kk,km,rw,ku,ky,lo,la,lv,lt,lb,mk,mg,ms,ml,mt,mi,mr,mn,my,ne,or,ps,fa,pa,sm,gd,sr,st,sn,sd,si,sl,so,su,sw,tg,ta,tt,te,tk,ur,ug,uz,cy,xh,yi,yo,zu".split(",")
    
    GEMINI_MODELS = {
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
        "Gemini 2.5 Pro": "gemini-2.5-pro",
        "Gemini 3 Flash": "gemini-3-flash-preview",
        "Gemini 3.1 Pro": "gemini-3.1-pro-preview",
        "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",
        "Gemini 3.5 Flash": "gemini-3.5-flash"
    }

    ACCENT_COLORS = {
        "Red": ("#e63946", "#b02a35"), "Orange": ("#f4a261", "#d68748"),
        "Yellow": ("#e9c46a", "#c2a154"), "Green": ("#2a9d8f", "#1f7a6f"),
        "Blue": ("#1f6aa5", "#144870"), "Indigo": ("#4b0082", "#320057"),
        "Violet": ("#9d4edd", "#7534a6")
    }

    # ==========================================
    # INITIALIZATION
    # ==========================================
    def __init__(self):
        super().__init__()
        self.title("MAnki v1.0")
        self.geometry("550x450") 
        self.minsize(550, 450)
        self.configure(fg_color=("#f5f5f5", "#2c2c2c"))

        self.anki = AnkiClient()
        self._init_state_variables()
        self.load_settings()
        
        ctk.set_appearance_mode(self.current_theme)
        self.toggle_resizable_visual()

        self.setup_animator()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_container = ctk.CTkFrame(self, fg_color=("#f5f5f5", "#2c2c2c"))
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.overlay_frame = ctk.CTkFrame(self, fg_color=("#cfcfcf", "#202020"), corner_radius=0)

        self.setup_main_ui()
        self.setup_settings_card()
        self.setup_log_card()
        
        self.apply_accent_color_visually(self.current_accent)
        self.apply_font_visually(self.current_font)

    def _init_state_variables(self):
        self.mining_state = "idle"
        self.mining_cancelled = False
        self.error_state_active = False
        self.warning_state_active = False
        self.api_keys = []
        
        self.active_key = ctk.StringVar(value="No keys selected")
        self.auto_switch_key = ctk.BooleanVar(value=False)
        self.current_gemini_model = "Gemini 3.1 Flash Lite"
        self.current_theme = "System"
        self.current_accent = "Blue"
        self.current_font = "Arial"
        self.resizable_window = ctk.BooleanVar(value=False)
        self.auto_tags = ctk.BooleanVar(value=True)
        self.mined_history = []
        
        self.default_prompt = (
            "You are a flashcard assistant. For the word provided, return STRICTLY a JSON object with these exact keys:\n"
            '"word": the word itself\n"sentence": a descriptive example sentence\n'
            '"definition": LANG definition\n"translation": YOUR_NATIVE_LANG translation\n'
            '"image_query": a visual description to find an image for this word (short and easy for stock photo providers)\n'
            "Return ONLY valid JSON without markdown blocks."
        )
        self.prepared_prompt = self.default_prompt
        self.anki_deck = ""
        self.anki_model = ""
        self.anki_audio_field = ""
        self.anki_image_field = ""

        self.available_image_providers = ["None", "Google Images", "IStock", "Unsplash", "Shutterstock", "Pexels", "GettyImages", "Adobe Stock", "Adobe Stock (No AI)", "Alamy"]
        self.current_image_provider = "None"
        self.waiting_for_image = False
        
        self.current_mining_note_id = None
        self.current_mining_word = ""
        self.current_image_query = ""
        self.current_image_query_actual = ""
        self.initial_clipboard_image = None
        self.pending_note_dict = None
        self.duplicate_check_after_id = None
        self.current_duplicate_query = ""
        self.previous_input_text = ""
        self.current_fade_id = 0

        self.available_tts_services = ["Cambridge (UK)", "Cambridge (US)", "Oxford (UK)", "Oxford (US)"] + [f"Google ({lang})" for lang in self.GOOGLE_LANGS]
        self.tts_chain = ["Google (en-US)"]

        # Temporary settings
        self.temp_api_keys = []
        self.temp_active_key = ctk.StringVar()
        self.temp_auto_switch = ctk.BooleanVar()
        self.temp_gemini_model = ctk.StringVar()
        self.temp_theme = ctk.StringVar()
        self.temp_accent = ctk.StringVar()
        self.temp_font = ctk.StringVar()
        self.temp_anki_deck = ctk.StringVar()
        self.temp_anki_model = ctk.StringVar()
        self.temp_anki_audio_field = ctk.StringVar()
        self.temp_anki_image_field = ctk.StringVar()
        self.temp_image_provider = ctk.StringVar()
        self.temp_tts_chain = []
        self.temp_resizable = ctk.BooleanVar()
        self.temp_auto_tags = ctk.BooleanVar()

    # ==========================================
    # ANIMATION & STYLING ENGINE
    # ==========================================
    def setup_animator(self):
        self.animated_buttons = []
        self.animated_inputs = []
        self.last_anim_time = time.time()
        self.animate_loop()

    def hex_to_rgb(self, hex_col):
        if not hex_col or hex_col == "transparent": return (128, 128, 128)
        if isinstance(hex_col, str):
            hex_col = hex_col.lstrip("#")
            if len(hex_col) == 3: hex_col = "".join([c*2 for c in hex_col])
            try: return tuple(int(hex_col[i:i+2], 16) for i in (0, 2, 4))
            except ValueError: pass
        return (128, 128, 128)

    def rgb_to_hex(self, rgb):
        return f"#{max(0, min(255, int(rgb[0]))):02x}{max(0, min(255, int(rgb[1]))):02x}{max(0, min(255, int(rgb[2]))):02x}"

    def register_button(self, btn):
        if hasattr(btn, "_smooth_hover_initialized"): return
        btn._smooth_hover_initialized = True
        
        orig_fg = btn.cget("fg_color")
        is_option = isinstance(btn, ctk.CTkOptionMenu)
        orig_hov = btn.cget("button_hover_color" if is_option else "hover_color") if hasattr(btn, "cget") else orig_fg
        
        btn.original_fg_color_tup = orig_fg if isinstance(orig_fg, (tuple, list)) else (orig_fg, orig_fg)
        btn.hover_color_tup = orig_hov if isinstance(orig_hov, (tuple, list)) else (orig_hov, orig_hov)
        btn._current_color_l = self.hex_to_rgb(btn.original_fg_color_tup[0])
        btn._current_color_d = self.hex_to_rgb(btn.original_fg_color_tup[1])
        
        btn.target_color_tup = btn.hover_color_tup if btn.cget("state") == "disabled" else btn.original_fg_color_tup
        if btn.cget("state") == "disabled":
            btn._current_color_l = self.hex_to_rgb(btn.hover_color_tup[0])
            btn._current_color_d = self.hex_to_rgb(btn.hover_color_tup[1])
            
        if not is_option:
            try: btn.configure(hover=False)
            except Exception: pass
        
        def set_target(color):
            if btn.cget("state") != "disabled": btn.target_color_tup = color
            
        btn.bind("<Enter>", lambda e: set_target(btn.hover_color_tup), add="+")
        btn.bind("<Leave>", lambda e: set_target(btn.original_fg_color_tup), add="+")
        if hasattr(btn, "_canvas"):
            btn._canvas.bind("<Enter>", lambda e: set_target(btn.hover_color_tup), add="+")
            btn._canvas.bind("<Leave>", lambda e: set_target(btn.original_fg_color_tup), add="+")
        if hasattr(btn, "_text_label"):
            btn._text_label.bind("<Enter>", lambda e: set_target(btn.hover_color_tup), add="+")
            btn._text_label.bind("<Leave>", lambda e: set_target(btn.original_fg_color_tup), add="+")

        self.animated_buttons.append(btn)

    def register_input(self, widget):
        if hasattr(widget, "_smooth_input_initialized"): return
        widget._smooth_input_initialized = True
        
        inner_widget = widget._entry if isinstance(widget, ctk.CTkEntry) else (widget._textbox if isinstance(widget, ctk.CTkTextbox) else None)
        orig_fg = widget.cget("fg_color")
        orig_fg = ("#f9f9fa", "#1d1e1e") if orig_fg in ("transparent", None) else orig_fg
        orig_fg_tup = orig_fg if isinstance(orig_fg, (tuple, list)) else (orig_fg, orig_fg)
        
        l_rgb, d_rgb = self.hex_to_rgb(orig_fg_tup[0]), self.hex_to_rgb(orig_fg_tup[1])
        focus_l_rgb, focus_d_rgb = tuple(max(0, c - 15) for c in l_rgb), tuple(min(255, c + 15) for c in d_rgb)
        
        widget.original_fg_color_tup = orig_fg_tup
        widget.focus_color_tup = (self.rgb_to_hex(focus_l_rgb), self.rgb_to_hex(focus_d_rgb))
        widget.target_color_tup = widget.original_fg_color_tup
        widget._current_color_l, widget._current_color_d = l_rgb, d_rgb
        
        widget.original_border_width = widget.cget("border_width") or 2
        widget.hover_border_width = widget.original_border_width + 2
        widget.target_border_width = widget.original_border_width
        widget._current_border_width = float(widget.original_border_width)
        widget._is_focused = False
        
        self.animated_inputs.append(widget)
        
        def on_hover(is_enter):
            if not getattr(widget, "_is_focused", False):
                widget.target_border_width = widget.hover_border_width if is_enter else widget.original_border_width
                
        def on_focus(is_focus):
            widget._is_focused = is_focus
            widget.target_border_width = widget.hover_border_width if is_focus else widget.original_border_width
            widget.target_color_tup = widget.focus_color_tup if is_focus else widget.original_fg_color_tup
            if inner_widget and inner_widget.winfo_exists():
                inner_widget.configure(insertofftime=0 if is_focus else 300)
                if is_focus: widget.after(400, lambda: inner_widget.configure(insertofftime=300) if getattr(widget, "_is_focused", False) and inner_widget.winfo_exists() else None)
            
        widget.bind("<Enter>", lambda e: on_hover(True), add="+")
        widget.bind("<Leave>", lambda e: on_hover(False), add="+")
        bind_target = inner_widget if inner_widget else widget
        bind_target.bind("<FocusIn>", lambda e: on_focus(True), add="+")
        bind_target.bind("<FocusOut>", lambda e: on_focus(False), add="+")
        if inner_widget:
            bind_target.bind("<Enter>", lambda e: on_hover(True), add="+")
            bind_target.bind("<Leave>", lambda e: on_hover(False), add="+")

    def animate_loop(self):
        now = time.time()
        dt, self.last_anim_time = now - getattr(self, "last_anim_time", now), now
        lerp_speed = min(16.0 * dt, 1.0)
        
        self.animated_buttons = self._update_animated_widgets(self.animated_buttons, lerp_speed, is_input=False)
        self.animated_inputs = self._update_animated_widgets(getattr(self, "animated_inputs", []), lerp_speed, is_input=True)
        self.after(7, self.animate_loop) 

    def _update_animated_widgets(self, widget_list, speed, is_input):
        active_widgets = []
        for w in widget_list:
            if not w or not w.winfo_exists(): continue
            active_widgets.append(w)
            try:
                if is_input:
                    cbw, tbw = w._current_border_width, w.target_border_width
                    if abs(cbw - tbw) > 0.1:
                        w._current_border_width += (tbw - cbw) * speed
                    else:
                        w._current_border_width = float(tbw)
                        
                    if w.cget("border_width") != int(round(w._current_border_width)):
                        w.configure(border_width=int(round(w._current_border_width)))
                        
                t_l, t_d = self.hex_to_rgb(w.target_color_tup[0]), self.hex_to_rgb(w.target_color_tup[1])
                c_l, c_d = w._current_color_l, w._current_color_d
                
                if sum(abs(c_l[i] - t_l[i]) + abs(c_d[i] - t_d[i]) for i in range(3)) > 1.0:
                    w._current_color_l = tuple(c + (t - c) * speed for c, t in zip(c_l, t_l))
                    w._current_color_d = tuple(c + (t - c) * speed for c, t in zip(c_d, t_d))
                    new_hex = (self.rgb_to_hex(w._current_color_l), self.rgb_to_hex(w._current_color_d))
                    
                    if isinstance(w, ctk.CTkOptionMenu): w.configure(fg_color=new_hex, button_color=new_hex)
                    else: w.configure(fg_color=new_hex)
                elif w.cget("fg_color") != w.target_color_tup and w.cget("state") != "disabled":
                    w._current_color_l, w._current_color_d = t_l, t_d
                    if isinstance(w, ctk.CTkOptionMenu): w.configure(fg_color=w.target_color_tup, button_color=w.target_color_tup)
                    else: w.configure(fg_color=w.target_color_tup)
            except Exception: continue
        return active_widgets

    def animate_button_press(self, button_widget, action_callback):
        if button_widget.cget("state") == "disabled": return
        try:
            button_widget._current_color_l = self.hex_to_rgb(button_widget.original_fg_color_tup[0])
            button_widget._current_color_d = self.hex_to_rgb(button_widget.original_fg_color_tup[1])
            if isinstance(button_widget, ctk.CTkOptionMenu):
                button_widget.configure(fg_color=button_widget.original_fg_color_tup, button_color=button_widget.original_fg_color_tup)
            else:
                button_widget.configure(fg_color=button_widget.original_fg_color_tup)
        except Exception: pass
        self.after(120, action_callback)

    def set_widget_state(self, widget, state):
        widget.configure(state=state)
        try: widget.configure(cursor="hand2" if state == "normal" else "arrow")
        except Exception: pass
        if hasattr(widget, "target_color_tup"):
            try:
                if not hasattr(widget, "original_fg_color_tup"):
                    orig_fg = widget.cget("fg_color")
                    widget.original_fg_color_tup = orig_fg if isinstance(orig_fg, (tuple, list)) else (orig_fg, orig_fg)
                if not hasattr(widget, "hover_color_tup"):
                    orig_hov = widget.cget("button_hover_color" if isinstance(widget, ctk.CTkOptionMenu) else "hover_color")
                    widget.hover_color_tup = orig_hov if isinstance(orig_hov, (tuple, list)) else (orig_hov, orig_hov)

                widget.target_color_tup = widget.hover_color_tup if state == "disabled" else widget.original_fg_color_tup
            except Exception: pass

    # ==========================================
    # SETTINGS MANAGEMENT
    # ==========================================
    def censor_key(self, key):
        return f"...{key[-4:]}" if key and key not in ["No keys selected", "No keys"] and len(key) >= 4 else "No keys selected"

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE): return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.api_keys = data.get("api_keys", [])
            raw_active = data.get("active_key", "No keys selected")
            self.active_key.set(self.censor_key(raw_active) if raw_active in self.api_keys else (self.censor_key(self.api_keys[0]) if self.api_keys else "No keys selected"))

            self.auto_switch_key.set(data.get("auto_switch", True))
            self.current_gemini_model = data.get("gemini_model", "Gemini 3.1 Flash Lite")
            if self.current_gemini_model not in self.GEMINI_MODELS: self.current_gemini_model = "Gemini 3.1 Flash Lite"

            self.current_theme = data.get("theme", "System")
            self.current_accent = data.get("accent_color", "Blue")
            self.current_font = data.get("font_family", "Arial")
            self.prepared_prompt = data.get("prepared_prompt", self.prepared_prompt)
            self.anki_deck = data.get("anki_deck", "")
            self.anki_model = data.get("anki_model", "")
            self.anki_audio_field = data.get("anki_audio_field", "")
            self.anki_image_field = data.get("anki_image_field", "")
            
            self.current_image_provider = data.get("image_provider", "None")
            if self.current_image_provider not in self.available_image_providers: self.current_image_provider = "None"
                
            self.resizable_window.set(data.get("resizable_window", False))
            self.auto_tags.set(data.get("auto_tags", True))
            
            self.tts_chain = [s for s in data.get("tts_chain", self.tts_chain) if s in self.available_tts_services]
            if not self.tts_chain: self.tts_chain = [""]
        except Exception as e:
            print(f"Failed to load settings: {e}")

    def save_settings(self):
        raw_active = next((k for k in self.api_keys if self.censor_key(k) == self.active_key.get()), "No keys selected")
        data = {
            "api_keys": self.api_keys, "active_key": raw_active,
            "auto_switch": self.auto_switch_key.get(), "gemini_model": self.current_gemini_model,
            "theme": self.current_theme, "accent_color": self.current_accent,
            "font_family": self.current_font, "prepared_prompt": self.prepared_prompt,
            "anki_deck": self.anki_deck, "anki_model": self.anki_model,
            "anki_audio_field": self.anki_audio_field, "anki_image_field": self.anki_image_field,
            "image_provider": self.current_image_provider, "tts_chain": self.tts_chain,
            "resizable_window": self.resizable_window.get(), "auto_tags": self.auto_tags.get()
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def apply_settings(self):
        is_resizable_changed = self.resizable_window.get() != self.temp_resizable.get()
        self.api_keys = self.temp_api_keys.copy()
        self.active_key.set(self.temp_active_key.get())
        self.auto_switch_key.set(self.temp_auto_switch.get())
        self.current_gemini_model = self.temp_gemini_model.get()
        self.current_theme = self.temp_theme.get()
        self.current_accent = self.temp_accent.get()
        self.current_font = self.temp_font.get()
        self.prepared_prompt = self.prompt_textbox.get("1.0", "end-1c")
        self.anki_deck = self.temp_anki_deck.get()
        self.anki_model = self.temp_anki_model.get()
        self.anki_audio_field = self.temp_anki_audio_field.get()
        self.anki_image_field = self.temp_anki_image_field.get()
        self.current_image_provider = self.temp_image_provider.get()
        self.tts_chain = self.temp_tts_chain.copy()
        self.resizable_window.set(self.temp_resizable.get())
        self.auto_tags.set(self.auto_tags.get())

        ctk.set_appearance_mode(self.current_theme)
        if is_resizable_changed: self.toggle_resizable_visual()
            
        self.apply_accent_color_visually(self.current_accent)
        self.apply_font_visually(self.current_font)
        self.save_settings()
        self.set_widget_state(self.apply_btn, "disabled")

    def done_settings(self):
        if self.apply_btn.cget("state") == "normal": self.apply_settings()
        self.hide_settings()
        
    def _on_temp_change(self, attr_name, value=None):
        if value is not None:
            attr = getattr(self, f"temp_{attr_name}")
            attr.set(value) if hasattr(attr, 'set') else setattr(self, f"temp_{attr_name}", value)
        
        if attr_name == 'anki_model': self.update_audio_fields(self.temp_anki_model.get())
        if attr_name == 'anki_image_field': self.update_image_provider_state()
        
        self.update_anki_menu_hovers()
        self.on_setting_changed()

    def on_setting_changed(self, event=None):
        changed = (
            self.temp_api_keys != self.api_keys or self.temp_active_key.get() != self.active_key.get() or
            self.temp_auto_switch.get() != self.auto_switch_key.get() or self.temp_gemini_model.get() != self.current_gemini_model or
            self.temp_theme.get() != self.current_theme or self.temp_accent.get() != self.current_accent or
            self.temp_font.get() != self.current_font or self.temp_anki_deck.get() != self.anki_deck or
            self.temp_anki_model.get() != self.anki_model or self.temp_anki_audio_field.get() != self.anki_audio_field or
            self.temp_anki_image_field.get() != self.anki_image_field or self.temp_image_provider.get() != self.current_image_provider or
            self.temp_tts_chain != self.tts_chain or self.temp_resizable.get() != self.resizable_window.get() or
            self.temp_auto_tags.get() != self.auto_tags.get() or self.prompt_textbox.get("1.0", "end-1c") != self.prepared_prompt
        )
        self.set_widget_state(self.apply_btn, "normal" if changed else "disabled")

    def toggle_resizable_visual(self):
        if self.resizable_window.get(): self.resizable(True, True)
        else:
            self.resizable(False, False)
            self.geometry("550x450")

    # ==========================================
    # UI BUILDERS & MANAGERS
    # ==========================================
    def _create_dropdown(self, parent, label_text, values, command_key, state="normal"):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(5, 5))
        lbl = ctk.CTkLabel(frame, text=label_text)
        lbl.pack(side="left", anchor="w")
        menu = ctk.CTkOptionMenu(
            frame, height=42, width=140, corner_radius=18, 
            values=values, text_color_disabled="#aeaeae", 
            cursor="hand2" if state == "normal" else "arrow", 
            command=lambda v: self._on_temp_change(command_key, v), state=state
        )
        if values: menu.set(values[0])
        menu.pack(side="right")
        self.register_button(menu)
        return frame, lbl, menu

    def setup_main_ui(self):
        self.brand_label = ctk.CTkLabel(self.main_container, text="🐵MAnki", text_color=("black", "white"))
        self.brand_label.place(relx=0.05, rely=0.05, anchor="nw")

        self.top_right_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.top_right_frame.place(relx=0.95, rely=0.05, anchor="ne")

        self.log_btn = ctk.CTkButton(
            self.top_right_frame, text=" 📜 ", width=45, height=55, corner_radius=22,
            fg_color=("#e0e0e0", "#363636"), hover_color=("#d5d5d5", "#454545"), 
            text_color=("black", "white"), text_color_disabled="#aeaeae", cursor="hand2", 
            command=lambda: self.animate_button_press(self.log_btn, self.show_log)
        )
        self.register_button(self.log_btn)
        self.log_btn.pack(side="left", padx=(0, 10))

        self.settings_btn = ctk.CTkButton(
            self.top_right_frame, text="⚙️", width=80, height=55, corner_radius=22,
            fg_color=("#e0e0e0", "#363636"), hover_color=("#d5d5d5", "#454545"), 
            text_color=("black", "white"), text_color_disabled="#aeaeae", cursor="hand2",
            command=lambda: self.animate_button_press(self.settings_btn, self.show_settings)
        )
        self.register_button(self.settings_btn)
        self.settings_btn.pack(side="left")

        self.duplicate_label = ctk.CTkLabel(self.main_container, text="", text_color="#e63946", cursor="hand2")
        self.duplicate_label.bind("<Button-1>", lambda e: self.anki.invoke("guiBrowse", query=self.current_duplicate_query))

        self.input_entry = ctk.CTkEntry(self.main_container, width=220, height=60, corner_radius=25, justify="center", placeholder_text="type here...")
        self.input_entry.place(relx=0.5, rely=0.42, anchor="center")
        self.input_entry.bind("<Return>", lambda event: self.process_request())
        self.input_entry.bind("<KeyRelease>", self.on_input_key_release)
        self.register_input(self.input_entry)
        self.default_entry_border_color = self.input_entry.cget("border_color")

        self.image_status_label = ctk.CTkLabel(self.main_container, text="", text_color="gray")
        self.image_status_label.place(relx=0.5, rely=0.54, anchor="center")

        self.image_query_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.image_query_link = ctk.CTkLabel(self.image_query_frame, text="", text_color=("#1a73e8", "#4da3ff"), cursor="hand2")
        self.image_query_entry = ctk.CTkEntry(self.image_query_frame, text_color=("black", "white"), fg_color="transparent", border_width=0, justify="center")
        self.register_input(self.image_query_entry)

        self.action_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.action_frame.place(relx=0.5, rely=0.75, anchor="center")

        self.send_btn = ctk.CTkButton(
            self.action_frame, text="⛏️ Mine", width=165, height=65, corner_radius=22,
            text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2",
            command=lambda: self.animate_button_press(self.send_btn, self.process_request)
        )
        self.register_button(self.send_btn)
        self.send_btn.pack(side="left", padx=(0, 10))

        self.paste_btn = ctk.CTkButton(
            self.action_frame, text="📋", width=65, height=65, corner_radius=22,
            text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2",
            command=lambda: self.animate_button_press(self.paste_btn, self.paste_and_mine)
        )
        self.register_button(self.paste_btn)
        self.paste_btn.pack(side="left", padx=(0, 10))

        self.edit_history_btn = ctk.CTkButton(
            self.action_frame, text="✐", width=71, height=65, corner_radius=22,
            text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2",
            command=lambda: self.animate_button_press(self.edit_history_btn, self.show_history_menu)
        )
        self.register_button(self.edit_history_btn)
        self.edit_history_btn.pack(side="left")

    def setup_settings_card(self):
        self.settings_card = ctk.CTkFrame(self.overlay_frame, corner_radius=28, fg_color=("#ffffff", "#2c2c2c"), bg_color="transparent", border_width=1, border_color=("gray80", "gray25"))
        self.settings_title = ctk.CTkLabel(self.settings_card, text="Settings")
        self.settings_title.pack(pady=(20, 10))

        self.settings_scroll_frame = ctk.CTkScrollableFrame(self.settings_card, fg_color="transparent", corner_radius=0)
        self.settings_scroll_frame.pack(fill="both", expand=True, padx=15, pady=5)

        api_label_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        api_label_frame.pack(anchor="w", padx=10, pady=(0, 5))
        self.lbl_gemini_title = ctk.CTkLabel(api_label_frame, text="Gemini ")
        self.lbl_gemini_title.pack(side="left")
        self.lbl_api_keys = ctk.CTkLabel(api_label_frame, text="API", text_color="#1a73e8", cursor="hand2")
        self.lbl_api_keys.bind("<Button-1>", lambda e: webbrowser.open_new("https://aistudio.google.com/api-keys"))
        self.lbl_api_keys.pack(side="left")

        _, self.lbl_gemini_model, self.gemini_model_menu = self._create_dropdown(self.settings_scroll_frame, "Model", list(self.GEMINI_MODELS.keys()), "gemini_model")
        self.gemini_model_menu.configure(width=180)

        key_select_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        key_select_frame.pack(fill="x", padx=10, pady=(5, 10))
        self.api_menu = ctk.CTkOptionMenu(key_select_frame, height=42, corner_radius=18, text_color_disabled="#aeaeae", cursor="hand2", command=lambda v: self._on_temp_change("active_key", v))
        self.register_button(self.api_menu)
        self.api_menu.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.del_btn = ctk.CTkButton(key_select_frame, text="✕", width=54, height=42, corner_radius=18, fg_color="#e63946", hover_color="#b02a35", text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.delete_api_key)
        self.register_button(self.del_btn)
        self.del_btn.pack(side="right")

        add_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        add_frame.pack(fill="x", padx=10, pady=(0, 15))
        self.api_entry = ctk.CTkEntry(add_frame, height=42, corner_radius=18, placeholder_text="New key...")
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.register_input(self.api_entry)
        
        self.add_btn = ctk.CTkButton(add_frame, text="＋", width=42, height=42, corner_radius=18, fg_color="#2a9d8f", hover_color="#1f7a6f", text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.add_api_key)
        self.register_button(self.add_btn)
        self.add_btn.pack(side="right")

        self.auto_switch_switch = ctk.CTkSwitch(self.settings_scroll_frame, text="Auto-switch API key on error", command=lambda: self._on_temp_change("auto_switch", self.auto_switch_switch.get() == 1))
        self.auto_switch_switch.pack(fill="x", padx=10, pady=(0, 20))

        self.lbl_tts_priority = ctk.CTkLabel(self.settings_scroll_frame, text="TTS")
        self.lbl_tts_priority.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.tts_search_entry = ctk.CTkEntry(self.settings_scroll_frame, height=42, corner_radius=18, placeholder_text="Search TTS...")
        self.tts_search_entry.pack(fill="x", padx=10, pady=(5, 5))
        self.tts_search_entry.bind("<KeyRelease>", self.filter_tts_services)
        self.register_input(self.tts_search_entry)

        tts_add_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        tts_add_frame.pack(fill="x", padx=10, pady=(5, 10))
        self.tts_menu = ctk.CTkOptionMenu(tts_add_frame, height=42, corner_radius=18, text_color_disabled="#aeaeae", cursor="hand2", values=self.available_tts_services)
        self.register_button(self.tts_menu)
        self.tts_menu.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.add_tts_btn = ctk.CTkButton(tts_add_frame, text="＋", width=42, height=42, corner_radius=18, fg_color="#2a9d8f", hover_color="#1f7a6f", text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.add_tts_service)
        self.register_button(self.add_tts_btn)
        self.add_tts_btn.pack(side="right")

        self.tts_list_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color=("#f1f1f1", "#333333"), corner_radius=10)
        self.tts_list_frame.pack(fill="x", padx=10, pady=(15, 20), ipadx=5, ipady=5)

        self.lbl_images = ctk.CTkLabel(self.settings_scroll_frame, text="Images")
        self.lbl_images.pack(anchor="w", padx=10, pady=(10, 5))
        _, self.lbl_image_provider, self.image_provider_menu = self._create_dropdown(self.settings_scroll_frame, "Image Provider", self.available_image_providers, "image_provider")

        self.lbl_ankiconnect = ctk.CTkLabel(self.settings_scroll_frame, text="AnkiConnect")
        self.lbl_ankiconnect.pack(anchor="w", padx=10, pady=(10, 5))
        anki_top_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        anki_top_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.anki_status_container = ctk.CTkFrame(anki_top_frame, fg_color="transparent")
        self.anki_status_container.pack(side="left", anchor="w")
        self.lbl_status_prefix = ctk.CTkLabel(self.anki_status_container, text="Status: ", text_color=("black", "white"))
        self.lbl_status_prefix.pack(side="left")
        self.lbl_status_value = ctk.CTkLabel(self.anki_status_container, text="Unknown❓")
        self.lbl_status_value.pack(side="left")
        self.lbl_status_link = ctk.CTkLabel(self.anki_status_container, text="")
        self.lbl_status_link.pack(side="left")
        self.lbl_status_right = ctk.CTkLabel(self.anki_status_container, text="")
        self.lbl_status_right.pack(side="left")
        self.lbl_status_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://ankiweb.net/shared/info/2055492159"))

        self.test_anki_btn = ctk.CTkButton(anki_top_frame, text="Test connection", width=140, height=42, corner_radius=18, text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.test_anki_connection)
        self.register_button(self.test_anki_btn)
        self.test_anki_btn.pack(side="right")

        self.anki_divider = ctk.CTkFrame(self.settings_scroll_frame, height=2, fg_color=("gray80", "gray25"))
        self.anki_divider.pack(fill="x", padx=10, pady=(5, 10))

        _, self.lbl_deck, self.deck_menu = self._create_dropdown(self.settings_scroll_frame, "Deck", ["—"], "anki_deck", "disabled")
        _, self.lbl_model, self.model_menu = self._create_dropdown(self.settings_scroll_frame, "Model", ["—"], "anki_model", "disabled")
        _, self.lbl_audio_field, self.audio_field_menu = self._create_dropdown(self.settings_scroll_frame, "Audio Field", ["—"], "anki_audio_field", "disabled")
        _, self.lbl_image_field, self.image_field_menu = self._create_dropdown(self.settings_scroll_frame, "Image Field", ["—"], "anki_image_field", "disabled")
        
        self.update_image_provider_state()

        self.auto_tags_switch = ctk.CTkSwitch(self.settings_scroll_frame, text="Enable Auto-tags (MAnki)", command=lambda: self._on_temp_change("auto_tags", self.auto_tags_switch.get() == 1))
        self.auto_tags_switch.pack(fill="x", padx=10, pady=(5, 15))

        self.lbl_prompt = ctk.CTkLabel(self.settings_scroll_frame, text="Prepared Prompt (Edit for your language and Anki template)")
        self.lbl_prompt.pack(anchor="w", padx=10, pady=(10, 5))
        self.prompt_textbox = ctk.CTkTextbox(self.settings_scroll_frame, height=140, corner_radius=20, border_width=2, fg_color=("#F9F9FA", "#343638"), border_color=("#979DA2", "#565B5E"), text_color=("black", "white"))
        self.prompt_textbox.pack(fill="x", padx=10, pady=(5, 15))
        self.prompt_textbox.bind("<KeyRelease>", self.on_setting_changed)
        self.register_input(self.prompt_textbox)

        self.lbl_appearance = ctk.CTkLabel(self.settings_scroll_frame, text="Appearance")
        self.lbl_appearance.pack(anchor="w", padx=10, pady=(10, 5))
        
        _, self.lbl_theme, self.theme_menu = self._create_dropdown(self.settings_scroll_frame, "Theme", ["System", "Light", "Dark"], "theme")
        _, self.lbl_accent_color, self.color_menu = self._create_dropdown(self.settings_scroll_frame, "Accent Color", list(self.ACCENT_COLORS.keys()), "accent")
        _, self.lbl_font_family, self.font_menu = self._create_dropdown(self.settings_scroll_frame, "Font", ["Segoe UI", "Arial", "Roboto"], "font")

        resizable_container = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        resizable_container.pack(fill="x", padx=10, pady=(5, 15))
        self.resizable_switch = ctk.CTkSwitch(resizable_container, text="Allow window resizing (laggy asf)", command=lambda: self._on_temp_change("resizable", self.resizable_switch.get() == 1))
        self.resizable_switch.pack(side="left")

        self.credits_lbl = ctk.CTkLabel(self.settings_scroll_frame, text="MAnki v1.0 / silly cat doralz", text_color="gray")
        self.credits_lbl.pack(pady=(20, 0), anchor="center")

        self.settings_bottom_frame = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.settings_bottom_frame.pack(side="bottom", fill="x", padx=20, pady=(10, 20))

        self.back_btn = ctk.CTkButton(self.settings_bottom_frame, text="Back", width=90, height=40, corner_radius=20, text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.hide_settings)
        self.register_button(self.back_btn)
        self.back_btn.pack(side="left")
        
        self.done_btn = ctk.CTkButton(self.settings_bottom_frame, text="Done", width=90, height=40, corner_radius=20, text_color="#ffffff", text_color_disabled="#aeaeae", cursor="hand2", command=self.done_settings)
        self.register_button(self.done_btn)
        self.done_btn.pack(side="right")
        
        self.apply_btn = ctk.CTkButton(self.settings_bottom_frame, text="Apply", width=90, height=40, corner_radius=20, text_color="#ffffff", text_color_disabled="#aeaeae", cursor="arrow", command=self.apply_settings, state="disabled")
        self.register_button(self.apply_btn)
        self.apply_btn.pack(side="right", padx=(0, 10))

    def setup_log_card(self):
        self.log_card = ctk.CTkFrame(self.overlay_frame, corner_radius=28, fg_color=("#ffffff", "#2c2c2c"), bg_color="transparent", border_width=1, border_color=("gray80", "gray25"))
        self.log_title = ctk.CTkLabel(self.log_card, text="Log")
        self.log_title.pack(pady=(20, 10))
        self.log_box = ctk.CTkTextbox(self.log_card, corner_radius=20, fg_color=("#f1f1f1", "gray20"), text_color=("black", "white"))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)
        self.log_box.configure(state="disabled")
        self.write_log("Everything seems to be okay for now")

        self.close_btn = ctk.CTkButton(self.log_card, text="Close", width=120, height=40, corner_radius=20, text_color=("white"), text_color_disabled="#aeaeae", cursor="hand2", command=self.hide_log)
        self.register_button(self.close_btn)
        self.close_btn.pack(side="bottom", pady=(10, 20))

    def apply_accent_color_visually(self, choice):
        fg, hover = self.ACCENT_COLORS[choice]
        buttons = [self.send_btn, self.paste_btn, getattr(self, 'edit_history_btn', None), self.close_btn, self.back_btn, self.apply_btn, self.done_btn, self.test_anki_btn]
        
        for btn in filter(None, buttons):
            btn.original_fg_color_tup, btn.hover_color_tup = (fg, fg), (hover, hover)
            btn.target_color_tup = btn.hover_color_tup if btn.cget("state") == "disabled" else btn.original_fg_color_tup

        for switch in [self.auto_switch_switch, self.resizable_switch, self.auto_tags_switch]:
            switch.configure(progress_color=fg)
        
        menus = [self.api_menu, self.gemini_model_menu, self.theme_menu, self.color_menu, self.font_menu, self.deck_menu, self.model_menu, self.audio_field_menu, self.image_field_menu, self.tts_menu, getattr(self, 'image_provider_menu', None)]
        for menu in filter(None, menus):
            menu.configure(text_color="#ffffff", button_hover_color=hover)
            if hasattr(menu, "target_color_tup"):
                val = menu.get() if hasattr(menu, "get") else ""
                is_disabled = menu.cget("state") == "disabled" or val in ["—", ""]
                menu.original_fg_color_tup = (hover, hover) if is_disabled else (fg, fg)
                menu.hover_color_tup = (hover, hover)
                menu.target_color_tup = menu.original_fg_color_tup
        
        if hasattr(self, 'update_anki_menu_hovers'): self.update_anki_menu_hovers()

    def apply_font_visually(self, font_name):
        self.brand_label.configure(font=(font_name, 43, "bold"))
        self.settings_title.configure(font=(font_name, 32, "bold"))
        self.log_title.configure(font=(font_name, 32, "bold"))
        
        for w in filter(None, [self.input_entry, self.paste_btn, getattr(self, 'edit_history_btn', None)]):
            w.configure(font=(font_name, 22))
            
        self.log_btn.configure(font=(font_name, 20))
        self.settings_btn.configure(font=(font_name, 18))
        self.send_btn.configure(font=(font_name, 22 if self.mining_state == "confirm_cancel" else 18, "bold"))
        
        for w in [self.del_btn, self.add_btn, self.add_tts_btn]:
            w.configure(font=(font_name, 16, "bold"))
            
        self.image_status_label.configure(font=(font_name, 15, "italic"))
        
        if hasattr(self, 'image_query_link'): 
            is_under = isinstance(self.image_query_link.cget("font"), tuple) and "underline" in self.image_query_link.cget("font")
            self.image_query_link.configure(font=(font_name, 14, "underline") if is_under else (font_name, 14))

        w_14 = [self.api_entry, self.lbl_gemini_model, self.auto_switch_switch, self.resizable_switch, self.auto_tags_switch, self.tts_search_entry, self.lbl_image_provider, self.lbl_status_prefix, self.lbl_status_value, self.test_anki_btn, self.lbl_deck, self.deck_menu, self.lbl_model, self.model_menu, self.lbl_audio_field, self.audio_field_menu, self.lbl_image_field, self.image_field_menu, self.lbl_theme, self.theme_menu, self.lbl_accent_color, self.color_menu, self.lbl_font_family, self.font_menu, self.log_box]
        for w in filter(None, w_14): w.configure(font=(font_name, 14))

        w_14_bold = [self.lbl_gemini_title, self.lbl_tts_priority, self.lbl_images, self.lbl_ankiconnect, self.lbl_appearance, self.lbl_prompt, self.back_btn, self.done_btn, self.apply_btn, self.close_btn]
        for w in filter(None, w_14_bold): w.configure(font=(font_name, 14, "bold"))

        self.lbl_api_keys.configure(font=(font_name, 14, "bold", "underline"))
        self.duplicate_label.configure(font=(font_name, 14, "underline"))

        w_13 = [self.api_menu, self.gemini_model_menu, self.tts_menu, getattr(self, 'image_provider_menu', None), self.prompt_textbox]
        for w in filter(None, w_13): w.configure(font=(font_name, 13))

        if hasattr(self, 'credits_lbl'): self.credits_lbl.configure(font=(font_name, 12, "italic"))
        self.refresh_tts_ui()

    def refresh_tts_ui(self):
        for widget in self.tts_list_frame.winfo_children(): widget.destroy()
        if not self.temp_tts_chain:
            ctk.CTkLabel(self.tts_list_frame, text="No TTS services selected", text_color="gray", font=(self.current_font, 13)).pack(pady=10)
            return

        chain_len = len(self.temp_tts_chain)
        for i, service in enumerate(self.temp_tts_chain):
            row = ctk.CTkFrame(self.tts_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(row, text=f"{i+1}. {service}", font=(self.current_font, 13, "bold"), text_color=("black", "white")).pack(side="left", padx=5)
            
            btn_del = ctk.CTkButton(row, text="✕", width=26, height=26, corner_radius=10, fg_color="#e63946", hover_color="#b02a35", text_color_disabled="#aeaeae", cursor="hand2", command=lambda s=service: self.remove_tts_service(s))
            self.register_button(btn_del)
            btn_del.pack(side="right", padx=(5, 0))
            
            down_state = "disabled" if i == chain_len - 1 or chain_len <= 1 else "normal"
            btn_down = ctk.CTkButton(row, text="↓", width=26, height=26, corner_radius=10, fg_color="#144870" if down_state == "disabled" else "#1f6aa5", hover_color="#144870", text_color_disabled="#aeaeae", state=down_state, cursor="arrow" if down_state == "disabled" else "hand2", command=lambda idx=i: self.move_tts(idx, 1))
            btn_down.original_fg_color_tup, btn_down.hover_color_tup = ("#1f6aa5", "#1f6aa5"), ("#144870", "#144870")
            self.register_button(btn_down)
            btn_down.pack(side="right", padx=2)
            
            up_state = "disabled" if i == 0 or chain_len <= 1 else "normal"
            btn_up = ctk.CTkButton(row, text="↑", width=26, height=26, corner_radius=10, fg_color="#144870" if up_state == "disabled" else "#1f6aa5", hover_color="#144870", text_color_disabled="#aeaeae", state=up_state, cursor="arrow" if up_state == "disabled" else "hand2", command=lambda idx=i: self.move_tts(idx, -1))
            btn_up.original_fg_color_tup, btn_up.hover_color_tup = ("#1f6aa5", "#1f6aa5"), ("#144870", "#144870")
            self.register_button(btn_up)
            btn_up.pack(side="right", padx=2)

    # ==========================================
    # POPUPS AND WINDOWS
    # ==========================================
    def show_log(self):
        if self.error_state_active or self.warning_state_active:
            self.error_state_active = self.warning_state_active = False
            self.log_btn.original_fg_color_tup, self.log_btn.hover_color_tup = ("#e0e0e0", "#363636"), ("#d5d5d5", "#454545")
            self.log_btn.target_color_tup = self.log_btn.original_fg_color_tup
            if self.image_status_label.cget("text") in ["Error happened, check the log", "Check the log"]:
                self.image_status_label.configure(text="")
                
        self.overlay_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.log_card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.90, relheight=0.90)
        self.focus()

    def hide_log(self):
        self.log_card.place_forget()
        self.overlay_frame.place_forget()
        
    def show_settings(self):
        self.temp_api_keys = self.api_keys.copy()
        self.temp_active_key.set(self.active_key.get())
        self.temp_auto_switch.set(self.auto_switch_key.get())
        self.temp_gemini_model.set(self.current_gemini_model)
        self.temp_theme.set(self.current_theme)
        self.temp_accent.set(self.current_accent)
        self.temp_font.set(self.current_font)
        self.temp_anki_deck.set(self.anki_deck)
        self.temp_anki_model.set(self.anki_model)
        self.temp_anki_audio_field.set(self.anki_audio_field)
        self.temp_anki_image_field.set(self.anki_image_field)
        self.temp_image_provider.set(self.current_image_provider)
        self.temp_tts_chain = self.tts_chain.copy()
        self.temp_resizable.set(self.resizable_window.get())
        self.temp_auto_tags.set(self.auto_tags.get())

        self.update_menu_values(temp_mode=True)
        self.auto_switch_switch.select() if self.temp_auto_switch.get() else self.auto_switch_switch.deselect()
        self.resizable_switch.select() if self.temp_resizable.get() else self.resizable_switch.deselect()
        self.auto_tags_switch.select() if self.temp_auto_tags.get() else self.auto_tags_switch.deselect()
        
        self.gemini_model_menu.set(self.current_gemini_model)
        self.theme_menu.set(self.temp_theme.get())
        self.color_menu.set(self.temp_accent.get())
        self.font_menu.set(self.temp_font.get())
        self.image_provider_menu.set(self.current_image_provider)
        
        self.test_anki_connection() 
        self.refresh_tts_ui()
        self.update_image_provider_state()
        self.update_anki_menu_hovers()

        if hasattr(self, 'prompt_textbox') and self.prompt_textbox.winfo_exists():
            self.prompt_textbox.delete("1.0", ctk.END)
            self.prompt_textbox.insert("1.0", self.prepared_prompt)

        self.set_widget_state(self.apply_btn, "disabled")
        self.overlay_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.settings_card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.90, relheight=0.90)
        
        try: self.settings_scroll_frame._parent_canvas.yview_moveto(0)
        except Exception: pass
            
        self.api_entry.configure(placeholder_text="New key...")
        self.tts_search_entry.configure(placeholder_text="Search TTS...")
        self.focus()

    def hide_settings(self):
        self.api_entry.delete(0, ctk.END)
        self.tts_search_entry.delete(0, ctk.END)
        self.filter_tts_services()
        self.settings_card.place_forget()
        self.overlay_frame.place_forget()

    def show_history_menu(self):
        menu = tk.Menu(self, tearoff=0)
        mode, fg, _ = ctk.get_appearance_mode(), self.ACCENT_COLORS[self.current_accent][0], None
        menu.configure(
            bg="#2c2c2c" if mode == "Dark" else "#ffffff", fg="#ffffff" if mode == "Dark" else "#000000", 
            activebackground=fg, activeforeground="#ffffff", font=(self.current_font, 13)
        )
        if not self.mined_history: menu.add_command(label="No words mined yet", state="disabled")
        else:
            for word, note_id in reversed(self.mined_history):
                menu.add_command(label=word, command=lambda nid=note_id: self.anki.invoke("guiEditNote", note=nid))
        menu.post(self.edit_history_btn.winfo_rootx(), self.edit_history_btn.winfo_rooty() + self.edit_history_btn.winfo_height())

    def open_image_search(self):
        if hasattr(self, 'current_image_url') and self.current_image_url: webbrowser.open_new(self.current_image_url)

    # ==========================================
    # ANKI & API LOGIC
    # ==========================================
    def update_image_provider_state(self):
        current_img_field = self.image_field_menu.get() if hasattr(self, 'image_field_menu') else "—"
        if current_img_field in ["None"]:
            self.image_provider_menu.configure(values=["—"])
            self.image_provider_menu.set("—")
            self.set_widget_state(self.image_provider_menu, "disabled")
        else:
            self.image_provider_menu.configure(values=self.available_image_providers)
            val = self.temp_image_provider.get()
            self.image_provider_menu.set(val if val in self.available_image_providers else "None")
            self.set_widget_state(self.image_provider_menu, "normal")
        if hasattr(self, 'update_anki_menu_hovers'): self.update_anki_menu_hovers()

    def update_anki_menu_hovers(self):
        fg, hover = self.ACCENT_COLORS[self.current_accent]
        for menu in filter(None, [self.deck_menu, self.model_menu, self.audio_field_menu, self.image_field_menu, self.tts_menu, getattr(self, 'image_provider_menu', None)]):
            if not hasattr(menu, "cget"): continue
            val = menu.get() if hasattr(menu, "get") else ""
            values = menu.cget("values") if hasattr(menu, "cget") else []
            is_disabled = values == ["—"] or menu.cget("state") == "disabled"
            self.set_widget_state(menu, "disabled" if is_disabled else "normal")
            menu.configure(button_hover_color=hover)
            if hasattr(menu, "target_color_tup"):
                menu.original_fg_color_tup = (hover, hover) if is_disabled or val in ["—", ""] else (fg, fg)
                menu.hover_color_tup = (hover, hover)
                menu.target_color_tup = menu.original_fg_color_tup

    def filter_tts_services(self, event=None):
        search = self.tts_search_entry.get().lower()
        filtered = [s for s in self.available_tts_services if search in s.lower()]
        self.tts_menu.configure(values=filtered)
        self.tts_menu.set(filtered[0] if filtered else "No match")

    def show_warning_state(self):
        if not self.error_state_active:
            self.warning_state_active = True
            self.log_btn.original_fg_color_tup, self.log_btn.hover_color_tup = ("#e9c46a", "#e9c46a"), ("#c2a154", "#c2a154")
            self.log_btn.target_color_tup = self.log_btn.original_fg_color_tup
            self.image_status_label.configure(text="Check the log", text_color="#e9c46a")

    def show_error_state(self):
        self.error_state_active, self.warning_state_active = True, False
        self.log_btn.original_fg_color_tup, self.log_btn.hover_color_tup = ("#e63946", "#e63946"), ("#b02a35", "#b02a35")
        self.log_btn.target_color_tup = self.log_btn.original_fg_color_tup
        self.image_status_label.configure(text="Error happened, check the log", text_color="#e63946")

    def on_input_key_release(self, event):
        current_text = self.input_entry.get()
        if current_text != getattr(self, "previous_input_text", ""):
            self.reset_duplicate_ui()
            self.previous_input_text = current_text
            if self.duplicate_check_after_id: self.after_cancel(self.duplicate_check_after_id)
            self.duplicate_check_after_id = self.after(1000, self.check_duplicate)
            
        new_width = max(220, len(current_text) * 12 + 40)
        max_width = self.winfo_width() - 40 if self.winfo_width() > 40 else 510
        self.input_entry.configure(width=min(new_width, max_width))

    def check_duplicate(self):
        word = self.input_entry.get().strip()
        if not word: self.reset_duplicate_ui()
        else: threading.Thread(target=self._async_check_duplicate, args=(word,), daemon=True).start()

    def _async_check_duplicate(self, word):
        if not self.anki_deck or not self.anki_model: return self.after(0, self.reset_duplicate_ui)
        model_fields = self.anki.invoke('modelFieldNames', modelName=self.anki_model)
        if not model_fields: return self.after(0, self.reset_duplicate_ui)
            
        first_field = model_fields[0]
        note_ids = self.anki.invoke('findNotes', query=f'deck:"{self.anki_deck}" note:"{self.anki_model}" "{first_field}:{word}"')
        
        if note_ids:
            for note in self.anki.invoke('notesInfo', notes=note_ids) or []:
                if re.sub(r'<[^>]+>', '', note.get('fields', {}).get(first_field, {}).get('value', '').strip()).lower() == word.lower():
                    return self.after(0, self.show_duplicate_ui, f'deck:"{self.anki_deck}" note:"{self.anki_model}" "{first_field}:{word}"', word)
        self.after(0, self.reset_duplicate_ui_if_matching, word)

    def show_duplicate_ui(self, query, checked_word):
        if self.input_entry.get().strip().lower() != checked_word.lower(): return
        self.current_duplicate_query = query
        self.duplicate_label.configure(text="Duplicate!")
        self.duplicate_label.place(relx=0.5, rely=0.33, anchor="center")
        self.input_entry.configure(border_color="#e63946")

    def reset_duplicate_ui_if_matching(self, checked_word):
        if self.input_entry.get().strip().lower() == checked_word.lower() or not self.input_entry.get().strip():
            self.reset_duplicate_ui()

    def reset_duplicate_ui(self):
        self.duplicate_label.place_forget()
        self.input_entry.configure(border_color=self.default_entry_border_color)

    def update_menu_values(self, temp_mode=False):
        keys_list = self.temp_api_keys if temp_mode else self.api_keys
        active_var = self.temp_active_key if temp_mode else self.active_key
        menu_values = [self.censor_key(k) for k in keys_list] if keys_list else ["No keys"]
        self.api_menu.configure(values=menu_values)
        
        current_choice = active_var.get()
        new_choice = current_choice if current_choice in menu_values else (menu_values[0] if keys_list else "No keys selected")
        active_var.set(new_choice)
        self.api_menu.set(new_choice)

    def add_api_key(self):
        new_key = self.api_entry.get().strip()
        if new_key and new_key not in self.temp_api_keys:
            self.temp_api_keys.append(new_key)
            self.update_menu_values(temp_mode=True)
            self.temp_active_key.set(self.censor_key(new_key))
            self.api_menu.set(self.censor_key(new_key))
            self.api_entry.delete(0, ctk.END)
            self.on_setting_changed()

    def delete_api_key(self):
        real_key = next((k for k in self.temp_api_keys if self.censor_key(k) == self.temp_active_key.get()), None)
        if real_key:
            self.temp_api_keys.remove(real_key)
            self.update_menu_values(temp_mode=True)
            self.on_setting_changed()

    def update_key_ui_from_thread(self, new_key):
        self.active_key.set(new_key)
        self.api_menu.set(new_key)
        self.save_settings()

    def add_tts_service(self):
        choice = self.tts_menu.get()
        if choice and choice != "No match" and choice not in self.temp_tts_chain:
            self.temp_tts_chain.append(choice)
            self.refresh_tts_ui(); self.on_setting_changed()

    def remove_tts_service(self, service):
        if service in self.temp_tts_chain:
            self.temp_tts_chain.remove(service)
            self.refresh_tts_ui(); self.on_setting_changed()

    def move_tts(self, index, direction):
        new_idx = index + direction
        if 0 <= new_idx < len(self.temp_tts_chain):
            self.temp_tts_chain[index], self.temp_tts_chain[new_idx] = self.temp_tts_chain[new_idx], self.temp_tts_chain[index]
            self.refresh_tts_ui(); self.on_setting_changed()

    def test_anki_connection(self):
        self.lbl_status_value.configure(text="❓ Unknown", text_color=("#000000", "#ffffff"))
        self.lbl_status_link.configure(text="", cursor="")
        self.lbl_status_right.configure(text="")
        
        for menu in [self.deck_menu, self.model_menu, self.audio_field_menu, self.image_field_menu]:
            self.set_widget_state(menu, "disabled")
            menu.configure(values=["—"])
            menu.set("—")
            
        self.update_image_provider_state(); self.update_anki_menu_hovers()

        def run_check():
            decks, models = self.anki.invoke('deckNames'), self.anki.invoke('modelNames')
            def update_ui():
                if decks is not None and models is not None:
                    self.lbl_status_value.configure(text="✔️ Connected", text_color="#2a9d8f")
                    self.lbl_status_link.configure(text="", cursor="")
                    self.lbl_status_right.configure(text="")
                    
                    self.set_widget_state(self.deck_menu, "normal")
                    self.deck_menu.configure(values=decks)
                    self.set_widget_state(self.model_menu, "normal")
                    self.model_menu.configure(values=models)
                    self.set_widget_state(self.audio_field_menu, "normal")
                    self.set_widget_state(self.image_field_menu, "normal")
                    
                    if self.temp_anki_deck.get() in decks: self.deck_menu.set(self.temp_anki_deck.get())
                    elif decks:
                        self.deck_menu.set(decks[0])
                        self.temp_anki_deck.set(decks[0])
                        
                    if self.temp_anki_model.get() in models:
                        self.model_menu.set(self.temp_anki_model.get())
                        self.update_audio_fields(self.temp_anki_model.get())
                    elif models:
                        self.model_menu.set(models[0])
                        self.temp_anki_model.set(models[0])
                        self.update_audio_fields(models[0])
                        
                    self.update_image_provider_state(); self.update_anki_menu_hovers(); self.on_setting_changed()
                else:
                    self.lbl_status_value.configure(text="❌ Error (Open Anki & Check ", text_color="#e63946")
                    self.lbl_status_link.configure(text="Addon", text_color="#1a73e8", cursor="hand2", font=(self.current_font, 14, "underline"))
                    self.lbl_status_right.configure(text=")", text_color="#e63946")

                    for menu in [self.deck_menu, self.model_menu, self.audio_field_menu, self.image_field_menu]:
                        self.set_widget_state(menu, "disabled")
                        menu.configure(values=["—"]); menu.set("—")
                    
                    self.update_image_provider_state(); self.update_anki_menu_hovers()
                    self.write_log("\n❌ AnkiConnect testing failed. Please open Anki and check the Addon.")
            self.after(0, update_ui)
        threading.Thread(target=run_check, daemon=True).start()

    def update_audio_fields(self, model_name):
        fields = self.anki.invoke('modelFieldNames', modelName=model_name)
        if fields:
            values = ["None"] + fields
            self.audio_field_menu.configure(values=values)
            self.audio_field_menu.set(self.temp_anki_audio_field.get() if self.temp_anki_audio_field.get() in values else "None")
            self.image_field_menu.configure(values=values)
            self.image_field_menu.set(self.temp_anki_image_field.get() if self.temp_anki_image_field.get() in values else "None")
        else:
            for menu in [self.audio_field_menu, self.image_field_menu]:
                menu.configure(values=["—"]); menu.set("—")
        self.update_image_provider_state(); self.update_anki_menu_hovers()

    def write_log(self, text, clear=False, trigger_warning=True):
        self.log_box.configure(state="normal")
        if clear: self.log_box.delete("1.0", ctk.END)
        self.log_box.insert(ctk.END, text + "\n")
        self.log_box.see(ctk.END)
        self.log_box.configure(state="disabled")
        if "⚠️" in text and trigger_warning: self.show_warning_state()

    def cancel_mining(self):
        self.mining_cancelled, self.waiting_for_image = True, False
        if hasattr(self, 'pending_note_dict') and self.pending_note_dict:
            self.write_log("\n⚠️ Mining cancelled before card creation.", trigger_warning=False)
            self.pending_note_dict = None
        elif self.current_mining_note_id:
            threading.Thread(target=self.anki.invoke, args=("deleteNotes",), kwargs={"notes": [self.current_mining_note_id]}, daemon=True).start()
            self.write_log(f"\n⚠️ Mining cancelled. Card {self.current_mining_note_id} deleted.", trigger_warning=False)
        else: self.write_log("\n⚠️ Mining cancelled before card creation.", trigger_warning=False)
            
        self.image_status_label.configure(text="")
        self.image_query_frame.place_forget()
        self.current_mining_note_id = None
        self.mining_state = "idle"
        self.reset_ui_state(); self.on_input_key_release(None)

    def revert_cancel_state(self):
        if self.mining_state == "confirm_cancel":
            self.mining_state = "mining"
            self.send_btn.configure(text="⛏️ Mining...", font=(self.current_font, 18, "bold"))
            fg, hover = self.ACCENT_COLORS[self.current_accent]
            self.send_btn.original_fg_color_tup, self.send_btn.hover_color_tup = (fg, fg), (hover, hover)
            self.send_btn.target_color_tup = self.send_btn.hover_color_tup

    def paste_and_mine(self):
        try:
            if clipboard_text := self.clipboard_get():
                self.input_entry.delete(0, ctk.END)
                self.input_entry.insert(0, clipboard_text)
                self.previous_input_text = clipboard_text
                self.process_request()
        except Exception as e:
            self.write_log(f"\nERR (Clipboard):\n{str(e)}"); self.show_error_state()

    def process_request(self):
        if self.mining_state == "idle":
            try:
                if self.anki.invoke('version') is None:
                    self.write_log("\n❌ Ошибка AnkiConnect. Убедитесь, что Anki открыта.")
                    return self.show_error_state()
            except Exception:
                self.write_log("\n❌ Ошибка подключения к AnkiConnect. Откройте Anki.")
                return self.show_error_state()

        if self.mining_state == "mining":
            self.mining_state = "confirm_cancel"
            self.send_btn.configure(text="❌Cancel?", font=(self.current_font, 22, "bold"))
            self.send_btn.original_fg_color_tup, self.send_btn.hover_color_tup = ("#e63946", "#e63946"), ("#b02a35", "#b02a35")
            self.send_btn.target_color_tup = self.send_btn.original_fg_color_tup
            
            if hasattr(self, 'cancel_timer_id') and self.cancel_timer_id: self.after_cancel(self.cancel_timer_id)
            self.cancel_timer_id = self.after(3000, self.revert_cancel_state)
            return
        elif self.mining_state == "confirm_cancel":
            if hasattr(self, 'cancel_timer_id') and self.cancel_timer_id: self.after_cancel(self.cancel_timer_id)
            return self.cancel_mining()

        if self.prepared_prompt.strip() == self.default_prompt.strip():
            messagebox.showwarning("MAnki", "Edit Prepared Prompt firstly")
            return self.show_settings()

        user_text = self.input_entry.get().strip()
        current_api_key = next((k for k in self.api_keys if self.censor_key(k) == self.active_key.get()), "")
        
        if not current_api_key:
            messagebox.showwarning("MAnki", "pls, add API key")
            return self.show_settings()
        if not user_text: return

        if self.duplicate_check_after_id: self.after_cancel(self.duplicate_check_after_id)
        self.reset_duplicate_ui()
        self.image_status_label.configure(text="")
        self.image_query_frame.place_forget()
        self.waiting_for_image = self.mining_cancelled = False
        self.current_mining_note_id = self.pending_note_dict = None
        self.current_fade_id += 1
        self.mining_state = "mining"
        
        self.set_widget_state(self.send_btn, "normal")
        self.send_btn.configure(text="⛏️ Mining...")
        self.send_btn.target_color_tup = self.send_btn.hover_color_tup
        
        self.write_log(f"\n----------------------------------------\nWord: {user_text}", clear=False)
        threading.Thread(target=self.fetch_from_api, args=(user_text, current_api_key), daemon=True).start()

    def fetch_from_api(self, text, initial_api_key):
        if self.mining_cancelled: return
        keys_to_try = [initial_api_key]
        if self.auto_switch_key.get(): keys_to_try.extend([k for k in self.api_keys if k != initial_api_key])
            
        for key in keys_to_try:
            if self.mining_cancelled: return
            try:
                if key != initial_api_key:
                    self.after(0, self.update_key_ui_from_thread, self.censor_key(key))
                    self.after(0, self.write_log, f"\n[Auto-Switch] Switching to API key: {self.censor_key(key)}...")
                
                model_api_name = self.GEMINI_MODELS.get(self.current_gemini_model, 'gemini-3.1-flash-lite')
                data = GeminiClient.generate_flashcard(text, key, self.prepared_prompt, model_api_name)
                
                if self.mining_cancelled: return
                return self.after(0, self.process_success_payload, data, text)
            except Exception as e:
                self.after(0, self.write_log, f"\nERR ({self.censor_key(key)}):\n{str(e)}")

        self.after(0, self.on_api_error, "All available API keys failed!")

    def process_success_payload(self, data, raw_word):
        if self.mining_cancelled: return
        try:
            word = data.get("word", raw_word)
            log_text = f"{word}\n{data.get('sentence', '')}\n{data.get('definition', '')}\n{data.get('translation', '')}"
            self.write_log(f"\nResult:\n{log_text}")
            
            if self.anki_deck and self.anki_model: threading.Thread(target=self.resolve_tts_and_export, args=(word, data), daemon=True).start()
            else:
                self.write_log("\n⚠️ Note not added: Deck or Model is not selected.")
                self.mining_state = "idle"; self.reset_ui_state()
        except Exception as e:
            self.write_log(f"\nData Processing Error:\n{str(e)}"); self.show_error_state()
            self.mining_state = "idle"; self.reset_ui_state()

    def resolve_tts_and_export(self, word, data):
        if self.mining_cancelled: return
        audio_url = None
        if self.anki_audio_field and self.anki_audio_field not in ["No fields", "None", "—", ""]:
            for service in self.tts_chain:
                if self.mining_cancelled: return
                audio_url = TTSProvider.get_audio_url(word, service)
                if audio_url:
                    self.after(0, self.write_log, f"[TTS] Fetched from {service}")
                    break
            if not audio_url and self.tts_chain: self.after(0, self.write_log, "⚠️ All configured TTS services failed.")
        else: self.after(0, self.write_log, "⏭️ Audio field is 'None', skipping TTS.")

        if self.mining_cancelled: return
        self.after(0, self.export_to_anki, data, audio_url)

    def export_to_anki(self, data, audio_url):
        if self.mining_cancelled: return
        model_fields = self.anki.invoke('modelFieldNames', modelName=self.anki_model)
        if not model_fields:
            self.write_log(f"\n❌ Error: Could not retrieve fields for '{self.anki_model}'"); self.show_error_state()
            self.mining_state = "idle"; self.reset_ui_state()
            return
            
        note_fields = {}
        for i, val in enumerate([data.get("word", ""), data.get("sentence", ""), data.get("definition", ""), data.get("translation", "")]):
            if i < len(model_fields): note_fields[model_fields[i]] = val
        
        note = {
            "deckName": self.anki_deck, "modelName": self.anki_model, "fields": note_fields,
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            "tags": ["MAnki"] if self.auto_tags.get() else []
        }
        
        if audio_url and self.anki_audio_field and self.anki_audio_field in model_fields:
            note["audio"] = [{"url": audio_url, "filename": f"manki_{data.get('word', 'word')}.mp3", "fields": [self.anki_audio_field]}]

        self.current_mining_word = data.get("word", "word")
        self.current_image_query_actual, self.current_image_query = data.get("image_query", ""), data.get("image_query", self.current_mining_word)
        requires_image = self.anki_image_field and self.anki_image_field not in ["No fields", "None", "—", ""]

        if requires_image:
            self.pending_note_dict = note
            self.after(0, self.start_waiting_for_image)
        else:
            self.pending_note_dict = None
            note_id = self.anki.invoke('addNote', note=note)
            
            if self.mining_cancelled:
                if note_id: self.anki.invoke("deleteNotes", notes=[note_id])
                return

            if note_id:
                self.write_log("\n✅ Successfully added to Anki")
                self.mined_history.append((self.current_mining_word, note_id))
            else:
                self.write_log("\n❌ Failed to add note (Duplicate or Anki error)."); self.show_error_state()
            self.mining_state = "idle"; self.reset_ui_state()

    def start_waiting_for_image(self):
        self.image_status_label.configure(text="Waiting for Image... (Copy any Image)", text_color="#e159ff")
        fallback_query, has_provider = getattr(self, "current_image_query", self.current_mining_word), self.current_image_provider not in ["None", "—"]
        
        self.image_query_link.pack_forget()
        self.image_query_link.unbind("<Button-1>")
        if hasattr(self, 'image_query_entry'): self.image_query_entry.pack_forget()
        
        if has_provider:
            self.image_query_link.configure(text=fallback_query, text_color=("#1a73e8", "#4da3ff"), font=(self.current_font, 14, "underline"), cursor="hand2")
            self.image_query_link.bind("<Button-1>", lambda e: self.open_image_search())
            self.image_query_link.pack(side="top")
            self.current_image_url = ImageProvider.get_image_url(fallback_query, self.current_image_provider)
        else:
            self.current_image_url = ""
            if getattr(self, "current_image_query_actual", ""):
                self.image_query_entry.configure(state="normal")
                self.image_query_entry.delete(0, "end")
                self.image_query_entry.insert(0, self.current_image_query_actual)
                self.image_query_entry.configure(state="readonly")
                self.image_query_entry.pack(side="top", fill="x", expand=True, pady=2)
                
        self.image_query_frame.place(relx=0.5, rely=0.60, anchor="center", relwidth=0.85)
        
        try: self.initial_clipboard_image = ImageGrab.grabclipboard()
        except Exception: self.initial_clipboard_image = None
            
        self.waiting_for_image = True; self.poll_clipboard_for_image()

    def poll_clipboard_for_image(self):
        if not self.waiting_for_image: return
        try:
            current_img = ImageGrab.grabclipboard()
            if current_img and isinstance(current_img, Image.Image):
                is_new = self.initial_clipboard_image is None or not isinstance(self.initial_clipboard_image, Image.Image) or current_img.size != self.initial_clipboard_image.size or current_img.tobytes() != self.initial_clipboard_image.tobytes()
                if is_new:
                    self.waiting_for_image = False
                    self.image_status_label.configure(text="Processing image...", text_color="gray")
                    self.image_query_frame.place_forget()
                    return threading.Thread(target=self.upload_image_to_anki, args=(current_img, self.current_mining_note_id, self.current_mining_word), daemon=True).start()
        except Exception as e: self.write_log(f"\n[Clipboard Error]: {str(e)}")
        self.after(500, self.poll_clipboard_for_image)

    def upload_image_to_anki(self, img, note_id, word):
        try:
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            filename = f"manki_img_{word.lower().replace(' ', '_')}_{int(time.time())}.png"
            
            if self.anki.invoke("storeMediaFile", filename=filename, data=img_base64):
                img_tag = f'<img src="{filename}">'
                if hasattr(self, 'pending_note_dict') and self.pending_note_dict:
                    self.pending_note_dict["fields"][self.anki_image_field] = img_tag
                    new_note_id = self.anki.invoke('addNote', note=self.pending_note_dict)
                    if new_note_id:
                        self.after(0, self.write_log, "\n✅ Successfully added to Anki with Image")
                        self.mined_history.append((word, new_note_id))
                        self.after(0, self.on_image_added_success, word)
                    else:
                        self.after(0, self.write_log, "\n❌ Failed to add note after storing media."); self.after(0, self.show_error_state); self.after(0, self.reset_after_image_failure)
                    self.pending_note_dict = None
                elif self.anki.invoke("updateNoteFields", note={"id": note_id, "fields": {self.anki_image_field: img_tag}}):
                    self.after(0, self.on_image_added_success, word)
                else:
                    self.after(0, self.write_log, f"\n❌ Failed to update fields for note {note_id}"); self.after(0, self.show_error_state); self.after(0, self.reset_after_image_failure)
            else:
                self.after(0, self.write_log, "\n❌ Failed to store media file in Anki"); self.after(0, self.show_error_state); self.after(0, self.reset_after_image_failure)
        except Exception as e:
            self.after(0, self.write_log, f"\n❌ Image export error: {str(e)}"); self.after(0, self.show_error_state); self.after(0, self.reset_after_image_failure)

    def on_image_added_success(self, word):
        self.image_status_label.configure(text=f'Word "{word}" has been added', text_color="#2a9d8f")
        self.image_query_frame.place_forget() 
        self.write_log(f'\n✅ "{word}" Successfully added to Anki')
        self.mining_state = "idle"
        self.reset_ui_state(); self.on_input_key_release(None)
        
        self.current_fade_id += 1
        fade_id = self.current_fade_id
        self.after(5000, lambda: self.start_fade_animation(fade_id))

    def reset_after_image_failure(self):
        self.mining_state = "idle"
        self.reset_ui_state(); self.on_input_key_release(None)

    def start_fade_animation(self, fade_id):
        if fade_id == self.current_fade_id: self.animate_text_fade(0, 20, fade_id)

    def animate_text_fade(self, step, total_steps, fade_id):
        if fade_id != self.current_fade_id: return
        if step > total_steps: return self.image_status_label.configure(text="")
            
        bg_hex = "#f5f5f5" if ctk.get_appearance_mode() == "Light" else "#2c2c2c"
        start_hex = "#2a9d8f" 
        r1, g1, b1 = (int(start_hex[i:i+2], 16) for i in (1, 3, 5))
        r2, g2, b2 = (int(bg_hex[i:i+2], 16) for i in (1, 3, 5))
        
        fraction = step / total_steps
        current_color = f"#{int(r1 + (r2 - r1) * fraction):02x}{int(g1 + (g2 - g1) * fraction):02x}{int(b1 + (b2 - b1) * fraction):02x}"
        self.image_status_label.configure(text_color=current_color)
        self.after(40, lambda: self.animate_text_fade(step + 1, total_steps, fade_id))

    def on_api_error(self, error_msg):
        self.write_log(f"\nFATAL ERR:\n{error_msg}")
        self.image_query_frame.place_forget()
        self.show_error_state()
        self.mining_state = "idle"; self.reset_ui_state()

    def reset_ui_state(self):
        self.input_entry.delete(0, ctk.END)
        self.previous_input_text = ""
        original_fg, original_hover = self.ACCENT_COLORS[self.current_accent]
        
        self.send_btn.configure(text="⛏️ Mine", font=(self.current_font, 18, "bold"))
        self.send_btn.original_fg_color_tup, self.send_btn.hover_color_tup = (original_fg, original_fg), (original_hover, original_hover)
        self.set_widget_state(self.send_btn, "normal")

if __name__ == "__main__":
    app = MAnkiClient()
    app.mainloop()
