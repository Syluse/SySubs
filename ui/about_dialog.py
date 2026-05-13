import customtkinter as ctk
import webbrowser
from constants import APP_VERSION, GITHUB_URL

class AboutDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("About SySubs")
        self.geometry("450x380")
        self.resizable(False, False)
        self.grab_set()

        self.after(100, lambda: self._center_on_parent(parent))
        self.after(200, lambda: self.iconbitmap("assets/icon.ico"))

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self, text="SySubs",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#CAF0F8"
        )
        header.grid(row=0, column=0, padx=30, pady=(30, 0))

        version_label = ctk.CTkLabel(
            self, text=f"Version {APP_VERSION}",
            font=ctk.CTkFont(size=14)
        )
        version_label.grid(row=1, column=0, padx=30, pady=(5, 15))

        desc = ctk.CTkLabel(
            self,
            text="Speech-to-text subtitle generator",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        desc.grid(row=2, column=0, padx=30, pady=(0, 15))

        credits_frame = ctk.CTkFrame(self, fg_color="transparent")
        credits_frame.grid(row=3, column=0, padx=30, sticky="ew")
        credits_frame.grid_columnconfigure(0, weight=1)

        credits_label = ctk.CTkLabel(
            credits_frame,
            text="Built with:\n\u2022 faster-whisper (OpenAI Whisper)\n\u2022 ffmpeg\n\u2022 CustomTkinter",
            font=ctk.CTkFont(size=12),
            justify="center",
            text_color=["#475569", "#94A3B8"]
        )
        credits_label.grid(row=0, column=0)

        social_label = ctk.CTkLabel(
            self, text="Created by Syluse",
            font=ctk.CTkFont(size=12),
            text_color=["#475569", "#94A3B8"]
        )
        social_label.grid(row=4, column=0, padx=30, pady=(15, 10))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=5, column=0, padx=30, pady=(10, 25))

        github_btn = ctk.CTkButton(
            btn_frame, text="Open GitHub", width=120,
            command=lambda: webbrowser.open(GITHUB_URL)
        )
        github_btn.pack(side="left", padx=5)

        close_btn = ctk.CTkButton(
            btn_frame, text="Close", width=120,
            command=self.destroy
        )
        close_btn.pack(side="left", padx=5)

    def _center_on_parent(self, parent):
        parent.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 450) // 2
        y = parent_y + (parent_h - 380) // 2
        self.geometry(f"450x380+{x}+{y}")
