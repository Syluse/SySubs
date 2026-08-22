import logging
import threading
import queue
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from constants import MODEL_REGISTRY, PROGRESS_COOLDOWN_S, MODEL_LOAD_TIMEOUT_S
from services.model_cache import ModelCache
from infra.audio_extractor import probe_duration, extract, AudioExtractionError
from infra.errors import friendly_error_message, TranscriptionError
from services.messages import ProgressMessage, LogMessage, PhaseMessage, ResultMessage, CancelledMessage, ErrorMessage

logger = logging.getLogger("sysubs")

class TranscriptionCancelledError(Exception):
    """Raised when transcription is cancelled by the user."""
    pass

class TranscriptionService:
    @staticmethod
    def run(file_path, model_name, language, device_info, models_path, progress_cb, stop_event,
            multilingual=False, lang_detect_threshold=0.5, lang_detect_segments=1):
        """Runs the full transcription pipeline."""
        if multilingual:
            registry_info = MODEL_REGISTRY.get(model_name)
            if registry_info and not registry_info.get("multilingual", False):
                logger.warning(
                    f"Model '{model_name}' does not reliably support multilingual "
                    "transcription; output may be poor."
                )

        logger.info("Probing audio file duration...")
        total_seconds = probe_duration(file_path)
        if total_seconds:
            logger.info(f"Duration: {total_seconds}s")
        else:
            logger.info("Could not determine duration; progress will be unknown.")

        model_dir = str(models_path / model_name)

        def _load_model():
            logger.info(f"Loading Whisper model '{model_name}' on {device_info.device} ({device_info.compute_type})...")
            return ModelCache.get(
                model_dir,
                device=device_info.device,
                compute_type=device_info.compute_type,
            )

        tmp_wav_path = None

        # try/finally guarantees the temp WAV is deleted on cancellation,
        # transcription errors, or generator close (GeneratorExit) alike.
        try:
            # Run extraction and model loading in parallel
            with ThreadPoolExecutor(max_workers=2) as executor:
                extract_future = executor.submit(extract, file_path)
                model_future = executor.submit(_load_model)
                tmp_wav_path = extract_future.result()

                # Poll the load future so Cancel stays responsive while the
                # model loads, and enforce a wall-clock budget — loads can
                # hang indefinitely on locked dirs or partial CUDA installs.
                # NOTE: a timed-out load thread keeps running (threads can't
                # be killed); it releases the cache lock when it finishes.
                deadline = time.monotonic() + MODEL_LOAD_TIMEOUT_S
                while True:
                    if stop_event.is_set():
                        raise TranscriptionCancelledError()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TranscriptionError(
                            f"Loading model '{model_name}' exceeded "
                            f"{MODEL_LOAD_TIMEOUT_S}s and may be stuck. Restart the app or check the models folder."
                        )
                    try:
                        model = model_future.result(timeout=min(remaining, 0.5))
                        break
                    except TimeoutError:
                        continue
                    except Exception as e:
                        if device_info.device != "cuda":
                            raise
                        logger.warning(f"CUDA init failed ({e}). Falling back to CPU...")
                        progress_cb(elapsed=0, total=total_seconds)
                        model = ModelCache.get(model_dir, device="cpu", compute_type="int8")
                        break

            logger.info(f"Audio extracted to: {tmp_wav_path}")
            logger.info("Model loaded successfully.")

            logger.info(f"Starting transcription for: {file_path}")
            segments, info = model.transcribe(
                tmp_wav_path,
                word_timestamps=True,
                language=None if multilingual else language,
                multilingual=multilingual,
                language_detection_threshold=lang_detect_threshold,
                language_detection_segments=lang_detect_segments,
            )
            logger.info(f"Transcribe returned. Detected language: {info.language}")

            lang_counts: dict[str, int] = {}
            for segment in segments:
                if stop_event.is_set():
                    raise TranscriptionCancelledError()

                progress_cb(elapsed=segment.end, total=total_seconds)

                seg_lang = getattr(segment, "language", None) or info.language
                lang_counts[seg_lang] = lang_counts.get(seg_lang, 0) + 1
                logger.debug(f"Segment [{seg_lang}]: {getattr(segment, 'text', '')[:60]}")

                if segment.words:
                    yield segment

            if lang_counts:
                summary = " ".join(f"{lang}({count})" for lang, count in sorted(lang_counts.items()))
                logger.info(f"Per-segment language breakdown: {summary}")
        finally:
            if tmp_wav_path and os.path.exists(tmp_wav_path):
                try:
                    Path(tmp_wav_path).unlink(missing_ok=True)
                    logger.debug(f"Deleted temporary audio file: {tmp_wav_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {tmp_wav_path}: {e}")

class TranscriptionWorker(threading.Thread):
    def __init__(self, result_queue, stop_event, file_path, model_name, language, 
                 device_info, models_path, preset_config, formatter_func, multilingual=False,
                 lang_detect_threshold=0.5, lang_detect_segments=1):
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
        self.multilingual = multilingual
        self.lang_detect_threshold = lang_detect_threshold
        self.lang_detect_segments = lang_detect_segments
        self.daemon = False # Allow finally-block cleanup on app exit
        self._last_progress_time = 0.0

    def run(self):
        try:
            self.queue.put(PhaseMessage(phase="load", message=f"Loading model {self.model_name}..."))

            def progress_cb(elapsed, total):
                now = time.monotonic()
                if now - self._last_progress_time < PROGRESS_COOLDOWN_S:
                    return
                self._last_progress_time = now
                self.queue.put(ProgressMessage(elapsed=elapsed, total=total))
            
            self.queue.put(LogMessage(message="Formatting subtitles..."))
            srt_string = self.formatter_func(
                TranscriptionService.run(
                    file_path=self.file_path,
                    model_name=self.model_name,
                    language=self.language,
                    device_info=self.device_info,
                    models_path=self.models_path,
                    progress_cb=progress_cb,
                    stop_event=self.stop_event,
                    multilingual=self.multilingual,
                    lang_detect_threshold=self.lang_detect_threshold,
                    lang_detect_segments=self.lang_detect_segments,
                ),
                self.preset_config,
            )

            self.queue.put(ResultMessage(srt=srt_string))

        except TranscriptionCancelledError:
            self.queue.put(CancelledMessage())
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            self.queue.put(ErrorMessage(message=friendly_error_message(e)))
