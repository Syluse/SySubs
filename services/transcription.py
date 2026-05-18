import logging
import threading
import queue
import os
from pathlib import Path
from services.model_service import SySubsError
from infra.audio_extractor import probe_duration, extract, AudioExtractionError

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger("sysubs")

class TranscriptionCancelledError(Exception):
    """Raised when transcription is cancelled by the user."""
    pass

class TranscriptionService:
    @staticmethod
    def run(file_path, model_name, language, device_info, models_path, progress_cb, stop_event):
        """Runs the full transcription pipeline."""
        if WhisperModel is None:
            raise SySubsError("faster-whisper is not installed.")

        # 1. Probe duration
        logger.info("Probing audio file duration...")
        total_seconds = probe_duration(file_path)
        logger.info(f"Duration: {total_seconds}s")
        
        # 2. Extract audio
        logger.info("Extracting audio to 16kHz mono WAV...")
        tmp_wav_path = extract(file_path)
        logger.info(f"Audio extracted to: {tmp_wav_path}")
        
        try:
            # 3. Load model
            model_dir = str(models_path / model_name)
            logger.info(f"Model directory: {model_dir}")
            try:
                logger.info(f"Loading Whisper model '{model_name}' on {device_info.device} ({device_info.compute_type})...")
                model = WhisperModel(
                    model_dir,
                    device=device_info.device,
                    compute_type=device_info.compute_type,
                    local_files_only=True,
                )
            except Exception as e:
                if device_info.device != "cuda":
                    raise
                logger.warning(f"CUDA init failed ({e}). Falling back to CPU...")
                progress_cb(elapsed=0, total=total_seconds)
                model = WhisperModel(
                    model_dir,
                    device="cpu",
                    compute_type="int8",
                    local_files_only=True,
                )
            logger.info("Model loaded successfully.")

            # 4. Transcribe
            logger.info(f"Starting transcription for: {file_path}")
            logger.info("Calling model.transcribe()...")
            # word_timestamps=True is required for our SubtitleFormatter to work as intended
            segments, info = model.transcribe(
                tmp_wav_path,
                word_timestamps=True,
                language=language
            )
            logger.info(f"Transcribe returned. Detected language: {info.language}")
            
            word_data = []
            for segment in segments:
                if stop_event.is_set():
                    raise TranscriptionCancelledError()
                
                # segment.end is the time in seconds from start of audio
                progress_cb(elapsed=segment.end, total=total_seconds)
                
                if segment.words:
                    word_data.append(segment)
            
            return word_data

        finally:
            # Cleanup tmp WAV
            if tmp_wav_path and os.path.exists(tmp_wav_path):
                try:
                    Path(tmp_wav_path).unlink(missing_ok=True)
                    logger.debug(f"Deleted temporary audio file: {tmp_wav_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {tmp_wav_path}: {e}")

class TranscriptionWorker(threading.Thread):
    def __init__(self, result_queue, stop_event, file_path, model_name, language, 
                 device_info, models_path, preset_config, formatter_func):
        super().__init__()
        self.queue = result_queue
        self.stop_event = stop_event
        self.file_path = file_path
        self.model_name = model_name
        self.language = language
        self.device_info = device_info
        self.models_path = models_path
        self.preset_config = preset_config
        self.formatter_func = formatter_func
        self.daemon = True # Ensure worker dies if main app closes

    def run(self):
        try:
            self.queue.put({"type": "log", "message": f"Loading model {self.model_name}..."})
            
            def progress_cb(elapsed, total):
                self.queue.put({
                    "type": "progress",
                    "elapsed": elapsed,
                    "total": total
                })
            
            # Run the service
            segments = TranscriptionService.run(
                file_path=self.file_path,
                model_name=self.model_name,
                language=self.language,
                device_info=self.device_info,
                models_path=self.models_path,
                progress_cb=progress_cb,
                stop_event=self.stop_event
            )
            
            # Format to SRT
            self.queue.put({"type": "log", "message": "Formatting subtitles..."})
            srt_string = self.formatter_func(segments, self.preset_config)
            
            self.queue.put({
                "type": "result",
                "srt": srt_string
            })
            
        except TranscriptionCancelledError:
            self.queue.put({"type": "cancelled"})
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            self.queue.put({
                "type": "error",
                "message": str(e)
            })
