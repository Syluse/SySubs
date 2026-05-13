import customtkinter as ctk
import os
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from constants import SUPPORTED_FORMATS, PRESETS, GITHUB_URL
from services.transcription import TranscriptionWorker
from services.subtitle_formatter import format_srt
from ui.model_manager import ModelManagerWindow

class MainWindow(ctk.CTk):
    def __init__(self, config, model_service, hardware_service, log_queue):
        super().__init__()
        self.config = config
        self.model_service = model_service
        self.hardware_service = hardware_service
        self.log_queue = log_queue
        
        self.title("SySubs")

        # Window geometry from config
        w = self.config.get("window_width", 950)
        h = self.config.get("window_height", 700)
        x = self.config.get("window_x")
        y = self.config.get("window_y")
        if x is not None and y is not None:
            self.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.geometry(f"{w}x{h}")

        self.after(200, lambda: self.iconbitmap("assets/icon.ico"))

        # Grid config — landscape layout
        self.grid_columnconfigure(0, weight=2)  # left panel
        self.grid_columnconfigure(1, weight=1)  # right panel (log)
        self.grid_rowconfigure(0, weight=0)     # header
        self.grid_rowconfigure(1, weight=1)     # content row

        self.minsize(850, 500)

        self._save_geom_timer = None
        self.bind("<Configure>", self._on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_menu()
        self._setup_ui()
        self._load_config_to_ui()
        
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.transcription_queue = queue.Queue()
        self.is_transcribing = False

    def _setup_ui(self):
        self.header_font = ctk.CTkFont(size=24, weight="bold")
        self.section_font = ctk.CTkFont(size=14, weight="bold")
        self.label_font = ctk.CTkFont(size=12)

        # 0. Header (spans both columns)
        self.header_label = ctk.CTkLabel(self, text="SySubs", font=self.header_font, text_color="#CAF0F8")
        self.header_label.grid(row=0, column=0, columnspan=2, padx=30, pady=(30, 20), sticky="w")

        # 1. Left Panel
        self.left_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.left_panel.grid(row=1, column=0, sticky="nsew", padx=(30, 15), pady=(0, 30))
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(0, weight=1)

        self.left_scroll = ctk.CTkScrollableFrame(self.left_panel)
        self.left_scroll.grid(row=0, column=0, sticky="nsew")
        self.left_scroll.grid_columnconfigure(0, weight=1)

        # -- File Section
        self.file_frame = ctk.CTkFrame(self.left_scroll)
        self.file_frame.grid(row=0, column=0, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.file_frame, text="INPUT FILE", font=self.section_font).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.inner_file_frame = ctk.CTkFrame(self.file_frame, fg_color="transparent")
        self.inner_file_frame.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.inner_file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_var = ctk.StringVar(value="No file selected")
        self.file_entry = ctk.CTkEntry(self.inner_file_frame, textvariable=self.file_path_var, state="readonly", height=35)
        self.file_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.browse_btn = ctk.CTkButton(self.inner_file_frame, text="Browse", width=100, height=35, command=self._on_browse)
        self.browse_btn.grid(row=0, column=1)

        # -- Config Section (2-column layout inside)
        self.config_frame = ctk.CTkFrame(self.left_scroll)
        self.config_frame.grid(row=1, column=0, pady=(20, 0), sticky="ew")
        self.config_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(self.config_frame, text="TRANSCRIPTION SETTINGS", font=self.section_font).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        # Model (row 1, col 0)
        ctk.CTkLabel(self.config_frame, text="Model", font=self.label_font).grid(row=1, column=0, padx=15, sticky="w")
        self.model_var = ctk.StringVar()
        self.model_dropdown = ctk.CTkOptionMenu(self.config_frame, variable=self.model_var, command=self._on_model_select, height=35)
        self.model_dropdown.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")
        self._refresh_models()

        # Language (row 1, col 1)
        ctk.CTkLabel(self.config_frame, text="Language", font=self.label_font).grid(row=1, column=1, padx=15, sticky="w")
        self.lang_var = ctk.StringVar(value="Auto-detect")
        self.lang_options = {
            "Auto-detect": None, "English": "en", "Filipino": "fil", "Japanese": "ja",
            "Spanish": "es", "French": "fr", "German": "de", "Korean": "ko",
            "Chinese": "zh", "Portuguese": "pt", "Italian": "it"
        }
        self.lang_dropdown = ctk.CTkOptionMenu(self.config_frame, values=list(self.lang_options.keys()), variable=self.lang_var, height=35)
        self.lang_dropdown.grid(row=2, column=1, padx=15, pady=(0, 15), sticky="ew")

        # Device (row 3, col 0)
        ctk.CTkLabel(self.config_frame, text="Device", font=self.label_font).grid(row=3, column=0, padx=15, sticky="w")
        self.device_var = ctk.StringVar(value="Auto")
        self.device_dropdown = ctk.CTkOptionMenu(
            self.config_frame,
            values=["Auto", "CPU", "CUDA"],
            variable=self.device_var,
            command=lambda v: self.config.set("device", v.lower()),
            height=35
        )
        self.device_dropdown.grid(row=4, column=0, padx=15, pady=(0, 15), sticky="ew")

        # Preset (row 3, col 1)
        ctk.CTkLabel(self.config_frame, text="Preset", font=self.label_font).grid(row=3, column=1, padx=15, sticky="w")
        self.preset_var = ctk.StringVar(value="Short-form / Reels")
        self.preset_options = {
            "Short-form / Reels": "short-form",
            "Landscape / YouTube": "landscape",
            "Custom": "custom"
        }
        self.preset_dropdown = ctk.CTkOptionMenu(
            self.config_frame,
            values=list(self.preset_options.keys()),
            variable=self.preset_var,
            command=self._on_preset_change,
            height=35
        )
        self.preset_dropdown.grid(row=4, column=1, padx=15, pady=(0, 15), sticky="ew")

        # Custom Settings (row 5, spans both columnspans)
        self.custom_frame = ctk.CTkFrame(self.config_frame, fg_color=["#F8FAFC", "#0F172A"], border_width=1)
        self.custom_frame.grid(row=5, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="ew")
        self.custom_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(self.custom_frame, text="Custom Mode", font=self.label_font).grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.custom_mode_var = ctk.StringVar(value="Words")
        self.custom_mode_dropdown = ctk.CTkOptionMenu(
            self.custom_frame,
            values=["Words", "Characters"],
            variable=self.custom_mode_var,
            command=lambda v: self.config.set("custom_mode", v.lower()),
            height=30
        )
        self.custom_mode_dropdown.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(self.custom_frame, text="Max Words/Chars", font=self.label_font).grid(row=0, column=1, padx=10, pady=(10, 0), sticky="w")
        self.custom_value_var = ctk.StringVar(value="2")
        self.custom_value_entry = ctk.CTkEntry(self.custom_frame, textvariable=self.custom_value_var, height=30)
        self.custom_value_entry.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")
        self.custom_value_var.trace_add("write", self._on_custom_value_write)

        ctk.CTkLabel(self.custom_frame, text="Max Lines", font=self.label_font).grid(row=0, column=2, padx=10, pady=(10, 0), sticky="w")
        self.custom_lines_var = ctk.StringVar(value="1")
        self.custom_lines_dropdown = ctk.CTkOptionMenu(
            self.custom_frame,
            values=["1", "2"],
            variable=self.custom_lines_var,
            command=lambda v: self.config.set("custom_max_lines", int(v)),
            height=30
        )
        self.custom_lines_dropdown.grid(row=1, column=2, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(self.custom_frame, text="Max Gap (seconds)", font=self.label_font).grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")
        self.custom_max_gap_var = ctk.StringVar(value="0.05")
        self.custom_max_gap_entry = ctk.CTkEntry(self.custom_frame, textvariable=self.custom_max_gap_var, height=30)
        self.custom_max_gap_entry.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.custom_max_gap_var.trace_add("write", self._on_custom_max_gap_write)
        self.custom_frame.grid_remove()

        # Text Formatting (row 6, spans both columnspans)
        self.format_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent", border_width=0)
        self.format_frame.grid(row=6, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="ew")
        self.format_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(self.format_frame, text="TEXT FORMATTING", font=self.section_font).grid(row=0, column=0, columnspan=2, sticky="w")

        ctk.CTkLabel(self.format_frame, text="Transform", font=self.label_font).grid(row=1, column=0, padx=(0, 5), sticky="w")
        self.transform_var = ctk.StringVar(value="None")
        self.transform_dropdown = ctk.CTkOptionMenu(
            self.format_frame,
            values=["None", "UPPERCASE", "lowercase"],
            variable=self.transform_var,
            command=lambda v: self.config.set("text_transform", {"None": "none", "UPPERCASE": "upper", "lowercase": "lower"}[v]),
            height=30
        )
        self.transform_dropdown.grid(row=2, column=0, padx=(0, 5), pady=(0, 5), sticky="ew")

        ctk.CTkLabel(self.format_frame, text="Remove Punctuations", font=self.label_font).grid(row=1, column=1, padx=(5, 0), sticky="w")
        self.strip_punct_var = ctk.BooleanVar(value=False)
        self.strip_punct_switch = ctk.CTkSwitch(
            self.format_frame,
            text="",
            variable=self.strip_punct_var,
            command=lambda: self.config.set("strip_punctuation", self.strip_punct_var.get()),
            switch_height=22,
            switch_width=44
        )
        self.strip_punct_switch.grid(row=2, column=1, padx=(5, 0), pady=(0, 5), sticky="w")

        # -- Action Button
        self.action_btn = ctk.CTkButton(
            self.left_scroll,
            text="Transcribe Now",
            font=ctk.CTkFont(size=18, weight="bold"),
            height=50,
            command=self._on_action_click,
            corner_radius=12
        )
        self.action_btn.grid(row=2, column=0, pady=(20, 10), sticky="ew")

        # -- Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.left_scroll, height=12)
        self.progress_bar.grid(row=3, column=0, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        # -- Bottom Actions
        self.bottom_frame = ctk.CTkFrame(self.left_scroll, fg_color="transparent")
        self.bottom_frame.grid(row=4, column=0, sticky="ew")
        self.bottom_frame.grid_columnconfigure(1, weight=1)

        self.reset_btn = ctk.CTkButton(self.bottom_frame, text="Reset to Defaults", width=120, fg_color="transparent", border_width=1, command=self._on_reset)
        self.reset_btn.grid(row=0, column=0, padx=(0, 10))

        self.mgr_btn = ctk.CTkButton(self.bottom_frame, text="Model Manager", width=140, fg_color="#2563EB", hover_color="#1D4ED8", command=self._on_open_manager)
        self.mgr_btn.grid(row=0, column=1, sticky="e")

        # 2. Right Panel (Activity Log)
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=1, column=1, sticky="nsew", padx=(15, 30), pady=(0, 30))
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.log_frame, text="ACTIVITY LOG", font=self.section_font).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.log_panel = ctk.CTkTextbox(self.log_frame, font=ctk.CTkFont(family="Consolas", size=11), state="disabled", border_width=0, fg_color="transparent")
        self.log_panel.grid(row=1, column=0, padx=5, pady=(0, 10), sticky="nsew")

    def _load_config_to_ui(self):
        # Lang
        lang_code = self.config.get("language")
        for label, code in self.lang_options.items():
            if code == lang_code:
                self.lang_var.set(label)
                break
        
        # Device
        device_code = self.config.get("device", "auto")
        self.device_var.set(device_code.capitalize())
        
        # Preset
        preset_code = self.config.get("preset", "short-form")
        for label, code in self.preset_options.items():
            if code == preset_code:
                self.preset_var.set(label)
                if code == "custom":
                    self.custom_frame.grid()
                else:
                    self.custom_frame.grid_remove()
                break
        
        # Custom Settings
        self.custom_mode_var.set(self.config.get("custom_mode", "words").capitalize())
        self.custom_value_var.set(str(self.config.get("custom_value", 2)))
        self.custom_lines_var.set(str(self.config.get("custom_max_lines", 1)))
        self.custom_max_gap_var.set(str(self.config.get("custom_max_gap", 0.05)))
        
        # Text Formatting
        transform = self.config.get("text_transform", "none")
        self.transform_var.set({"none": "None", "upper": "UPPERCASE", "lower": "lowercase"}[transform])
        self.strip_punct_var.set(self.config.get("strip_punctuation", False))
        
        # Model (refreshed in _refresh_models)
        self.model_var.set(self.config.get("model", "tiny"))

    def _refresh_models(self):
        downloaded = [m['name'] for m in self.model_service.list_models() if m['downloaded']]
        if not downloaded:
            self.model_dropdown.configure(values=["No models found"])
            self.model_var.set("No models found")
        else:
            self.model_dropdown.configure(values=downloaded)
            current = self.config.get("model")
            if current in downloaded:
                self.model_var.set(current)
            else:
                self.model_var.set(downloaded[0])
                self.config.set("model", downloaded[0])

    def _on_browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video/Audio Files", " ".join(SUPPORTED_FORMATS))]
        )
        if path:
            self.file_path_var.set(path)
            # Pre-set last folder?
            self.config.set("last_export_folder", str(Path(path).parent))

    def _on_model_select(self, choice):
        if choice != "No models found":
            self.config.set("model", choice)

    def _on_preset_change(self, choice):
        preset_code = self.preset_options[choice]
        self.config.set("preset", preset_code)
        
        if preset_code == "custom":
            self.custom_frame.grid()
        else:
            self.custom_frame.grid_remove()

    def _on_custom_value_write(self, *args):
        try:
            val = int(self.custom_value_var.get())
            if val > 0:
                self.config.set("custom_value", val)
        except ValueError:
            pass

    def _on_custom_max_gap_write(self, *args):
        try:
            val = float(self.custom_max_gap_var.get())
            if val >= 0:
                self.config.set("custom_max_gap", val)
        except ValueError:
            pass

    def _on_reset(self):
        if messagebox.askyesno("Reset", "Are you sure you want to reset all settings to defaults?"):
            self.config.reset()
            self._load_config_to_ui()
            self._refresh_models()
            self._log_to_ui("Settings reset to defaults.")

    def _on_action_click(self):
        if self.is_transcribing:
            self._cancel_transcription()
        else:
            self._start_transcription()

    def _start_transcription(self):
        file_path = self.file_path_var.get()
        if not os.path.exists(file_path):
            messagebox.showwarning("No File", "Please select a valid video or audio file first.")
            return
            
        model_name = self.model_var.get()
        if model_name == "No models found":
            messagebox.showwarning("No Model", "Please download a model first in the Model Manager.")
            return

        # NEW: Prompt for save location first
        source_path = Path(file_path)
        default_name = source_path.stem + ".srt"
        save_path = filedialog.asksaveasfilename(
            initialdir=source_path.parent,
            initialfile=default_name,
            title="Save Subtitles As",
            filetypes=[("Subtitle Files", "*.srt")]
        )
        
        if not save_path:
            return # User cancelled
            
        self.target_save_path = save_path

        # Prepare UI
        self.is_transcribing = True
        self.action_btn.configure(text="Cancel", fg_color="red")
        self.progress_bar.grid()
        self.progress_bar.set(0)
        self._set_controls_state("disabled")
        
        # Config
        self.config.set("language", self.lang_options[self.lang_var.get()])
        preset_code = self.preset_options[self.preset_var.get()]
        self.config.set("preset", preset_code)
        
        # Resolve Preset Config
        if preset_code == "custom":
            try:
                val = int(self.custom_value_var.get() or 1)
            except ValueError:
                val = 1
                
            preset_config = {
                "mode": self.custom_mode_var.get().lower() == "characters" and "chars" or "words",
                "value": val,
                "max_lines": int(self.custom_lines_var.get()),
                "long_word_threshold": 10,
                "max_gap": max(0, float(self.custom_max_gap_var.get() or 0)),
            }
        else:
            preset_config = PRESETS[preset_code]
        
        # Inject text formatting
        transform_key = self.transform_var.get()
        preset_config["text_transform"] = {"None": "none", "UPPERCASE": "upper", "lowercase": "lower"}[transform_key]
        preset_config["strip_punctuation"] = self.strip_punct_var.get()
        
        # Hardware
        device_info = self.hardware_service.resolve(self.config.get("device", "auto"))
        
        # Start Worker
        self.stop_event.clear()
        self.worker_thread = TranscriptionWorker(
            result_queue=self.transcription_queue,
            stop_event=self.stop_event,
            file_path=file_path,
            model_name=model_name,
            language=self.config.get("language"),
            device_info=device_info,
            models_path=self.model_service.models_path,
            preset_config=preset_config,
            formatter_func=format_srt
        )
        self.worker_thread.start()
        
        self.after(100, self._poll_queues)

    def _cancel_transcription(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self._log_to_ui("Cancelling transcription...")
            self.stop_event.set()
            self.action_btn.configure(state="disabled", text="Cancelling...")

    def _poll_queues(self):
        # 1. Drain Log Queue (from LogManager)
        while True:
            try:
                record = self.log_queue.get_nowait()
                self._log_to_ui(record.msg)
            except queue.Empty:
                break
                
        # 2. Drain Transcription Queue (from Worker)
        finished = False
        while True:
            try:
                msg = self.transcription_queue.get_nowait()
                if msg["type"] == "progress":
                    self.progress_bar.set(msg["elapsed"] / msg["total"])
                    # progress text in log?
                elif msg["type"] == "log":
                    self._log_to_ui(msg["message"])
                elif msg["type"] == "result":
                    self._handle_result(msg["srt"])
                    finished = True
                elif msg["type"] == "cancelled":
                    self._log_to_ui("Transcription cancelled.")
                    finished = True
                elif msg["type"] == "error":
                    self._log_to_ui(f"ERROR: {msg['message']}")
                    messagebox.showerror("Transcription Error", msg["message"])
                    finished = True
            except queue.Empty:
                break
        
        if finished:
            self._reset_ui()
        else:
            self.after(100, self._poll_queues)

    def _handle_result(self, srt_content):
        save_path = self.target_save_path
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            self._log_to_ui(f"Successfully saved to: {save_path}")
            messagebox.showinfo("Success", f"Subtitles exported to:\n{save_path}")
        except Exception as e:
            self._log_to_ui(f"Failed to save file: {e}")
            messagebox.showerror("Save Error", str(e))

    def _reset_ui(self):
        self.is_transcribing = False
        self.action_btn.configure(text="Transcribe", fg_color=["#3B8ED0", "#1F6AA5"], state="normal")
        self.progress_bar.grid_remove()
        self._set_controls_state("normal")
        self._refresh_models()

    def _set_controls_state(self, state):
        self.browse_btn.configure(state=state)
        self.model_dropdown.configure(state=state)
        self.lang_dropdown.configure(state=state)
        self.device_dropdown.configure(state=state)
        self.preset_dropdown.configure(state=state)
        self.mgr_btn.configure(state=state)
        self.reset_btn.configure(state=state)

    def _log_to_ui(self, message):
        self.log_panel.configure(state="normal")
        self.log_panel.insert("end", f"{message}\n")
        self.log_panel.see("end")
        self.log_panel.configure(state="disabled")

    def _on_open_manager(self):
        ModelManagerWindow(self, self.model_service, self.config, on_change_callback=self._refresh_models)

    def _setup_menu(self):
        menu_bg = "#1E293B"
        menu_fg = "#F8FAFC"
        menu_active_bg = "#334155"
        menu_active_fg = "#CAF0F8"

        menubar = tk.Menu(self, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg, activeforeground=menu_active_fg, font=("Segoe UI", 10), borderwidth=0, relief="flat")
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg, activeforeground=menu_active_fg, font=("Segoe UI", 10), borderwidth=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open File...", command=self._on_browse, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_menu_exit)

        help_menu = tk.Menu(menubar, tearoff=False, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg, activeforeground=menu_active_fg, font=("Segoe UI", 10), borderwidth=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Model Manager", command=self._on_open_manager, accelerator="Ctrl+Shift+M")
        help_menu.add_separator()
        help_menu.add_command(label="Report a Bug", command=lambda: webbrowser.open(GITHUB_URL + "/issues/new"))
        help_menu.add_command(label="Send Feedback", command=lambda: webbrowser.open(GITHUB_URL + "/discussions"))
        help_menu.add_separator()
        help_menu.add_command(label="About SySubs", command=self._on_about)

        self.bind("<Control-o>", lambda e: self._on_browse())
        self.bind("<Control-O>", lambda e: self._on_browse())
        self.bind("<Control-Shift-M>", lambda e: self._on_open_manager())
        self.bind("<Control-Shift-m>", lambda e: self._on_open_manager())

    def _on_menu_exit(self):
        self._on_close()

    def _on_about(self):
        from ui.about_dialog import AboutDialog
        AboutDialog(self)

    def _on_close(self):
        if self.is_transcribing:
            if not messagebox.askyesno("Quit?", "Transcription is in progress. Are you sure you want to quit?"):
                return
            self.stop_event.set()
        self._save_window_geometry()
        self.destroy()

    def _on_window_configure(self, event):
        if event.widget is not self:
            return
        if self._save_geom_timer:
            self.after_cancel(self._save_geom_timer)
        self._save_geom_timer = self.after(500, self._save_window_geometry)

    def _save_window_geometry(self):
        self.config.set("window_width", self.winfo_width())
        self.config.set("window_height", self.winfo_height())
        self.config.set("window_x", self.winfo_x())
        self.config.set("window_y", self.winfo_y())
