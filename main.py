import sys
import logging
import traceback
from tkinter import messagebox
import customtkinter as ctk

from infra.log_manager import setup_logging, ui_queue
from infra.config_manager import ConfigManager
from services.model_service import ModelService
from services import hardware_service
from ui.main_window import MainWindow

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
        
        # 0. Setup CUDA paths (Windows dev fix)
        hardware_service.setup_cuda_path()
        
        # 1b. Load Theme
        try:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("assets/theme.json")
        except Exception as e:
            logger.warning(f"Failed to load custom theme: {e}")
        
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
        
        # Show error box if possible
        try:
            import customtkinter as ctk
            root = ctk.CTk()
            root.withdraw()
            messagebox.showerror("SySubs Startup Error", error_msg)
        except:
            pass
            
        sys.exit(1)

if __name__ == "__main__":
    main()
