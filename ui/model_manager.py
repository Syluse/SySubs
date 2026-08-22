import customtkinter as ctk
import threading
import queue
import logging
import time
from tkinter import messagebox
from constants import DOWNLOAD_POLL_MS, MODEL_DOWNLOAD_TIMEOUT_S
from services.model_service import SySubsError

logger = logging.getLogger("sysubs")

def _fmt_elapsed(seconds: float) -> str:
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"

class ModelManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, model_service, config, on_change_callback=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.model_service = model_service
        self.config = config
        self.on_change_callback = on_change_callback
        
        self.title("Model Manager")
        self.geometry("600x500")
        
        self.grab_set()
        self.after(200, lambda: self.iconbitmap("assets/icon.ico"))
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.header = ctk.CTkLabel(self, text="Available Whisper Models", font=ctk.CTkFont(size=18, weight="bold"))
        self.header.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.scrollable_frame = ctk.CTkScrollableFrame(self)
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        
        self.rows = {}
        self.download_queues = {}
        self._downloading = set()
        self._download_started = {}
        
        self._render_models()
        self._poll_downloads()

    def _render_models(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        models = self.model_service.list_models()
        active_model = self.config.get("model")
        
        for i, m in enumerate(models):
            frame = ctk.CTkFrame(self.scrollable_frame)
            frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            frame.grid_columnconfigure(0, weight=1)
            
            multi_tag = " [multilingual]" if m.get("multilingual") else ""
            info_text = f"{m['name'].upper()}{multi_tag}: {m['size_mb']}MB\n{m['tier']}"
            info_label = ctk.CTkLabel(frame, text=info_text, justify="left", font=ctk.CTkFont(size=12))
            info_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
            
            status_frame = ctk.CTkFrame(frame, fg_color="transparent")
            status_frame.grid(row=0, column=1, padx=10, pady=10)
            
            status_text = "Downloaded" if m['downloaded'] else "Not Downloaded"
            status_color = "green" if m['downloaded'] else "gray"
            status_label = ctk.CTkLabel(status_frame, text=status_text, text_color=status_color, font=ctk.CTkFont(weight="bold"))
            status_label.grid(row=0, column=0, columnspan=2, pady=(0, 5))
            
            dl_btn = ctk.CTkButton(
                status_frame, 
                text="Download", 
                width=100,
                command=lambda name=m['name']: self._start_download(name)
            )
            if m['downloaded']:
                dl_btn.grid_forget()
            else:
                dl_btn.grid(row=1, column=0, padx=2)
                
            del_btn = ctk.CTkButton(
                status_frame, 
                text="Delete", 
                width=100, 
                fg_color="transparent", 
                border_width=1,
                command=lambda name=m['name']: self._delete_model(name)
            )
            if m['downloaded']:
                del_btn.grid(row=1, column=0, padx=2)
                if m['name'] == active_model:
                    del_btn.configure(state="disabled")
            else:
                del_btn.grid_forget()

            self.rows[m['name']] = {
                "frame": frame,
                "status_label": status_label,
                "dl_btn": dl_btn,
                "del_btn": del_btn
            }

    def _start_download(self, model_name):
        if model_name in self._downloading:
            return
        self._downloading.add(model_name)
        row = self.rows[model_name]
        row["dl_btn"].configure(state="disabled", text="Queued...")
        row["status_label"].configure(text="Downloading...", text_color="orange")

        q = queue.Queue()
        self.download_queues[model_name] = q
        self._download_started[model_name] = time.monotonic()

        def run_dl():
            try:
                self.model_service.download(model_name)
                q.put({"type": "success"})
            except Exception as e:
                q.put({"type": "error", "message": str(e)})

        threading.Thread(target=run_dl, daemon=True).start()

    def _delete_model(self, model_name):
        row = self.rows.get(model_name)
        try:
            self.model_service.delete(model_name)
            self._render_models()
            if self.on_change_callback:
                self.on_change_callback()
        except SySubsError as e:
            # A failed delete leaves the model on disk — surface it in the UI
            # (inline + dialog) instead of failing silently.
            logger.error(f"Delete failed: {e}")
            if row:
                lbl = row["status_label"]
                lbl.configure(text=f"Delete failed: {str(e)[:40]}", text_color="red")
                self.after(5000, lambda: self._restore_downloaded_status(lbl))
            messagebox.showerror("Delete Failed", str(e))

    def _restore_downloaded_status(self, label):
        """Restores the 'Downloaded' badge after an inline error (guarded
        against the widget having been re-rendered or destroyed)."""
        try:
            label.configure(text="Downloaded", text_color="green")
        except Exception:
            pass

    def _poll_downloads(self):
        active_names = set()
        now = time.monotonic()

        for name, q in list(self.download_queues.items()):
            active_names.add(name)
            try:
                msg = q.get_nowait()
                if msg["type"] == "success":
                    logger.info(f"Download finished for {name}")
                    self._downloading.discard(name)
                    self._download_started.pop(name, None)
                    del self.download_queues[name]
                    self._render_models()
                    if self.on_change_callback:
                        self.on_change_callback()
                elif msg["type"] == "error":
                    logger.error(f"Download failed for {name}: {msg['message']}")
                    self._downloading.discard(name)
                    self._download_started.pop(name, None)
                    del self.download_queues[name]
                    self._render_models()
                    self.rows[name]["status_label"].configure(text=f"Error: {msg['message'][:20]}...", text_color="red")
            except queue.Empty:
                # Watchdog: flag downloads that exceed the wall-clock budget.
                # The worker thread is left alone (its late result is still
                # processed if it ever arrives), so no double-download races.
                started = self._download_started.get(name)
                if started is not None and now - started > MODEL_DOWNLOAD_TIMEOUT_S:
                    elapsed = _fmt_elapsed(now - started)
                    logger.warning(f"Download of '{name}' exceeded {elapsed} — flagged as timed out.")
                    row = self.rows.get(name)
                    if row:
                        row["status_label"].configure(
                            text=f"Timed out after {elapsed} — still running...",
                            text_color="orange",
                        )
                    self._download_started[name] = now  # re-arm so we don't spam every tick

        self.after(DOWNLOAD_POLL_MS, self._poll_downloads)
