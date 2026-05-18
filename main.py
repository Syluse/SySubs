import sys
import os
import ctypes
import logging
import traceback
from tkinter import messagebox
import customtkinter as ctk

from infra.log_manager import setup_logging, ui_queue
from infra.config_manager import ConfigManager
from services.model_service import ModelService
from services import hardware_service
from ui.main_window import MainWindow

# Follow me on Twitch pls :D https://www.twitch.tv/syluse
# And on twitter https://twitter.com/syluse_
# It's ok if you don't want to, not like I'm pouting or anything hmp b-baka! >_>

# Set Windows taskbar app ID so the icon appears instead of default python icon
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("syluse.sysubs.1")
except Exception:
    pass

def main():
    # 1. Setup Logging
    try:
        logger = setup_logging()
    except Exception as e:
        # Fallback print if logging fails
        print(f"Critical error setting up logging: {e}")
        sys.exit(1)

    try:
        logger.info("SySubs starting boot sequence...")
        
        # 0a. Force offline mode to prevent HF network hangs in frozen builds
        os.environ["HF_HUB_OFFLINE"] = "1"
        
        # 0b. Setup CUDA paths (Windows dev fix)
        hardware_service.setup_cuda_path()
        
        # 1b. Set appearance
        ctk.set_appearance_mode("dark")
        
        # 2. Init Infra
        config = ConfigManager.get_instance()
        
        # 3. Init Services
        model_service = ModelService(config)
        device_info = hardware_service.detect()
        logger.info(f"Hardware detected: {device_info.device} ({device_info.compute_type})")
        
        # 4. Launch UI
        app = MainWindow(config, model_service, hardware_service, ui_queue)
        
        logger.info("Application ready.")
        app.mainloop()
        
    except Exception as e:
        error_msg = f"A critical error occurred during startup:\n\n{e}\n\n{traceback.format_exc()}"
        logger.critical(error_msg)

        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("SySubs Startup Error", error_msg)
        except:
            pass

        sys.exit(1)

if __name__ == "__main__":
    main()
