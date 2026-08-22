# SySubs TODO — Improvement Implementation Plan

> Generated from IMPROVEMENTS.md (sections 5, 7, 8 — 60+ findings consolidated below).
> Phases are ordered by priority and dependency. Each phase is independently shippable.

---

## Phase 1: Critical Reliability (P1)

- [x] **1.1 Graceful worker shutdown on exit** (7.1.1, ties 5.5.4)
  - Make `TranscriptionWorker` non-daemon (`services/transcription.py:123`)
  - In `_on_close` (`ui/main_window.py:744`): signal `stop_event` → `join(timeout=5)`
  - Register `atexit` hook to sweep orphaned `%TEMP%\sysubs_*.wav` files
- [ ] **1.2 Model load timeout + cancel path** (7.1.3)
  - Emit per-phase status: "Loading model 'small' (CPU/int8)…" via worker queue
  - Enforce wall-clock timeout on `ModelCache.get()` (e.g., 120s)
  - Expose Cancel during model load (check `stop_event` before/after load)

---

## Phase 2: High-Impact Fixes (P2)

- [x] **2.1 Indeterminate progress when duration unknown** (7.1.2)
  - When `total is None`, switch `progress_bar` to indeterminate/pulsing mode
- [x] **2.2 CUDA PATH dedup** (7.1.5)
  - In `setup_cuda_path()` (`services/hardware_service.py:28`): build candidate list,
    dedupe, prepend once. Avoid substring PATH check.
- [x] **2.3 Model download integrity** (7.2.1)
  - Post-download: verify file count / size against HF repo manifest
  - On mismatch: delete partial dir, re-prompt user
- [x] **2.4 Typed worker message protocol** (7.3.1)
  - Replace stringly-typed dicts with dataclasses (or constants) in a shared module
  - Affects: `TranscriptionWorker` emit sites + `MainWindow._poll_queues` switch
- [x] **2.5 Device-switch model caching** (7.1.4)
  - Keep up to N loaded model variants with LRU eviction
  - Or: warn user before triggering a reload

---

## Phase 3: Architecture & Code Quality (P3)

- [x] **3.1 Centralize error handling** (5.1.1)
  - Create `infra/errors.py`: typed hierarchy + `friendly_error_message(exc)` translator
  - Replace raw `Exception` / string forwarding in `_handle_result`
- [x] **3.2 Preset dataclass** (5.1.2)
  - Replace `dict`-based preset config with a `Preset` dataclass
  - Affects: `constants.py` PRESETS → `main_window.py` assembly → `subtitle_formatter.py`
- [ ] **3.3 `ModelInfo` typed registry** (5.1.3)
  - `NamedTuple` or `frozen dataclass` for `MODEL_REGISTRY` entries
- [x] **3.4 Validate config on load** (5.4.6)
  - Coerce types, drop unknown keys with warning log in `ConfigManager._load()`
- [ ] **3.5 De-duplicate model-refresh logic** (5.4.4)
  - Single function owns dropdown population; called from all mutation points
- [ ] **3.6 Break up oversized UI methods** (7.4.1)
  - Extract `_setup_ui` sections into `_build_file_section()`, `_build_config_section()`, etc.
  - Split `_start_transcription` into `prepare_config()` / `resolve_preset()` / `spawn_worker()`
- [x] **3.7 Named constants for magic numbers/sentinels** (7.4.2)
  - `MIN_GAP_SECONDS`, `UI_POLL_MS`, `DOWNLOAD_POLL_MS`, widget sizes
  - Replace sentinel strings with enum/dataclass
- [x] **3.8 Stream segments to formatter** (7.3.4)
  - Feed words to `format_srt` incrementally instead of collecting all segments first
- [ ] **3.9 Add `ruff`/`black` + CI lint gate** (7.4.4)
  - Dev-only deps; enforce import style + formatting consistency

---

## Phase 4: UX Improvements (P3)

- [x] **4.1 Remember last-used folder for Browse dialog** (5.3.5)
  - Pass `initialdir=self.config.get("last_export_folder")` to `askopenfilename`
- [x] **4.2 Reduce custom-settings input friction** (5.3.6)
  - Switch `trace_add("write")` → `FocusOut` binding; surface validation errors
- [x] **4.3 Keyboard shortcuts** (5.3.7, 8.4.3)
  - `Ctrl+Enter`/`Ctrl+T` → Transcribe, `Ctrl+1/2/3` → presets, `Ctrl+D` → Reset (Ctrl+S for Save still pending)
- [x] **4.4 Log panel colorization** (5.3.8, 8.4.4)
  - Pass `LogRecord.levelname` through queue; apply text tags in `_log_to_ui`
- [x] **4.5 Estimated time remaining** (5.3.3)
  - Display `ETA = (total - elapsed) * (wall_clock / elapsed)` in log area
- [ ] **4.6 Auto-download prompt for missing models** (5.3.4)
  - When selected model isn't downloaded, prompt with size → route to download flow
- [ ] **4.7 Batch transcription queue** (5.3.2)
  - `deque` of jobs + "Stop after current" toggle; reuse model cache
- [x] **4.8 Per-segment language logging** (5.7.5)
  - Collect `segment.language`/`language_probability`, log DEBUG per segment + INFO summary
- [x] **4.9 Model tooltip / multilingual column** (5.7.7)
  - Dropdown tooltip + "Multilingual" ✓/✗ column in model manager

---

## Phase 5: Security Hardening (P3)

- [x] **5.1 `resolve("cuda")` must validate CUDA runtime** (8.2.1)
  - Call `_cuda_runtime_available()` inside `resolve()` before returning CUDA DeviceInfo
- [x] **5.2 Harden `ctypes.CDLL` loading** (7.2.2)
  - Restrict DLL search to known-good dirs (system CUDA, pip `nvidia-*` bins)

---

## Phase 6: Edge Cases & Bug Fixes (P3)

- [x] **6.1 Fix cancel race** (8.1.1)
  - Add `_cancelled` flag; check before processing queued result messages
- [x] **6.2 Model download timeout** (8.1.2)
  - UI watchdog flags downloads exceeding MODEL_DOWNLOAD_TIMEOUT_S (30 min) inline; worker thread finishes naturally (no kill), late results still processed
- [x] **6.3 Guard against double-click Download** (8.1.3)
  - Disable Download button or track in-flight downloads per model
- [x] **6.4 Remove dead `PRESETS["multilingual"]`** (8.2.2)
  - Either add to dropdown or remove from constants + handle stale config values
- [x] **6.5 Fix `_pre_multilingual_lang` restore** (8.2.3)
  - Fall back to `"Auto-detect"` when prior value is missing/invalid
- [x] **6.6 Initialize `target_save_path` in `__init__`** (8.2.4)
- [x] **6.7 Don't save geometry when minimized** (8.2.5)
  - Check `window_state() != "iconic"` before saving width/height
- [x] **6.8 Use `round()` in `_format_srt_time`** (8.2.6)
  - `int(td.microseconds / 1000)` → `round(td.microseconds / 1000)`
- [x] **6.9 Move SRT write off main thread** (8.4.1)
  - Write file in background or yield with `after(0)`

---

## Phase 7: Build & CI (P3)

- [x] **7.1 Smoke-test built zip in CI** (5.5.2)
  - Extract + launch with timeout; assert process stays alive
- [x] **7.2 Add SHA-256 checksum to release artifacts** (5.5.3)
- [x] **7.3 Pin ffmpeg download URL in CI** (8.4.5)
  - Replace `latest` auto-redirect with specific version tag
- [x] **7.4 Validate system Python version in `package.ps1`** (8.3.1)
  - Assert version matches embeddable Python before copying Tcl/Tk DLLs
- [x] **7.5 Fix `_pth` glob fragility** (8.3.2)
  - Use `Select-Object -First 1` to handle multiple matches
- [x] **7.6 Stop tracking `Releases/` in git** (8.3.3)
  - Verify `.gitignore` pattern; purge from history if committed
- [x] **7.7 Run tests in CI** (8.3.4)
  - Remove `tests/**` from `.gitignore` (or keep local-only) + add `pytest` stage to workflow
- [x] **7.8 Align CI `download_model` API** (8.3.5)
  - Use `WhisperModel.download_model` instead of legacy `faster_whisper.utils.download_model`

---

## Phase 8: Performance (P3)

- [x] **8.1 Parallelize audio extraction + model loading** (5.2.2)
  - Spawn model load in second thread; join with extraction result

---

## Already Completed

- [x] Text transform (uppercase/lowercase) option
- [x] Strip punctuation option
- [x] Combined transform + strip
- [x] Formatting UI controls
- [x] Persist formatting preferences
- [x] Initialize Git repo + .gitignore
- [x] Create GitHub repository
- [x] Build spec / script
- [x] GitHub Releases workflow
- [x] Model caching (5.2.1 — v1.2.0)
- [x] Multilingual improvements (5.7.1–5.7.4, 5.7.6 — v1.2.0)
- [x] Dependency pinning (5.5.1 — v1.2.0)
- [x] Unit tests (5.4.2 — v1.2.0)
- [x] Drag & drop (5.3.1 — v1.2.0)

---

## Deferred / Future (v2+)

- [ ] Batch file processing (covered by 4.7 — queue infrastructure)
- [ ] SRT preview + editing before export
- [ ] Auto-update mechanism (GitHub Releases API)
- [ ] Speaker diarization
- [ ] Translation mode
- [ ] Update Downloader (from original TODO)
