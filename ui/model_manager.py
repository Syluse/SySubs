import customtkinter as ctk
import threading
import queue
import logging
from services.model_service import SySubsError

logger = logging.getLogger("sysubs")

class ModelManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, model_service, config, on_change_callback=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.model_service = model_service
        self.config = config
        self.on_change_callback = on_change_callback
        
        self.title("Model Manager")
        self.geometry("600x500")
        
        # Modal-ish behavior
        self.grab_set()
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header = ctk.CTkLabel(self, text="Available Whisper Models", font=ctk.CTkFont(size=18, weight="bold"))
        self.header.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        # Scrollable list container
        self.scrollable_frame = ctk.CTkScrollableFrame(self)
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        
        self.rows = {} # model_name -> widgets dict
        self.download_queues = {} # model_name -> queue
        
        self._render_models()
        self._poll_downloads()

    def _render_models(self):
        # Clear existing
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        models = self.model_service.list_models()
        active_model = self.config.get("model")
        
        for i, m in enumerate(models):
            frame = ctk.CTkFrame(self.scrollable_frame)
            frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            frame.grid_columnconfigure(0, weight=1)
            
            # Left: Info
            info_text = f"{m['name'].upper()}: {m['size_mb']}MB\n{m['tier']}"
            info_label = ctk.CTkLabel(frame, text=info_text, justify="left", font=ctk.CTkFont(size=12))
            info_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
            
            # Right: Status & Actions
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
        row = self.rows[model_name]
        row["dl_btn"].configure(state="disabled", text="Queued...")
        row["status_label"].configure(text="Downloading...", text_color="orange")
        
        q = queue.Queue()
        self.download_queues[model_name] = q
        
        def run_dl():
            try:
                # model_service.download currently doesn't support progress_cb for faster-whisper easily,
                # but we'll call it for when we add it.
                self.model_service.download(model_name)
                q.put({"type": "success"})
            except Exception as e:
                q.put({"type": "error", "message": str(e)})

        threading.Thread(target=run_dl, daemon=True).start()

    def _delete_model(self, model_name):
        try:
            self.model_service.delete(model_name)
            self._render_models()
            if self.on_change_callback:
                self.on_change_callback()
        except SySubsError as e:
            logger.error(f"Delete failed: {e}")
            # Could show a messagebox here

    def _poll_downloads(self):
        for name, q in list(self.download_queues.items()):
            try:
                msg = q.get_nowait()
                if msg["type"] == "success":
                    logger.info(f"Download thread finished for {name}")
                    del self.download_queues[name]
                    self._render_models()
                    if self.on_change_callback:
                        self.on_change_callback()
                elif msg["type"] == "error":
                    logger.error(f"Download failed for {name}: {msg['message']}")
                    del self.download_queues[name]
                    self._render_models()
                    # Show error on row
                    self.rows[name]["status_label"].configure(text=f"Error: {msg['message'][:20]}...", text_color="red")
            except queue.Empty:
                pass
        
        self.after(500, self._poll_downloads)
