"""Tests for services/hardware_service.py — mock ctranslate2/ctypes branches."""

import sys
from types import SimpleNamespace

import pytest

from services import hardware_service as hs

_REAL_CUDA_RUNTIME = hs._cuda_runtime_available


class FakeCTranslate2:
    def __init__(self, count=None, raises=False):
        self._count = count
        self._raises = raises

    def get_cuda_device_count(self):
        if self._raises:
            raise RuntimeError("ctranslate2 exploded")
        return self._count


@pytest.fixture(autouse=True)
def _no_path_mutations(monkeypatch):
    monkeypatch.setattr(hs, "setup_cuda_path", lambda: None)
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: False)
    yield
    monkeypatch.setattr(hs, "ctranslate2", None)


def test_detect_falls_back_to_cpu_without_ctranslate2(monkeypatch):
    monkeypatch.setattr(hs, "ctranslate2", None)
    info = hs.detect()
    assert (info.device, info.compute_type, info.cuda_available) == ("cpu", "int8", False)


def test_detect_cpu_when_no_cuda_device(monkeypatch):
    monkeypatch.setattr(hs, "ctranslate2", FakeCTranslate2(count=0))
    info = hs.detect()
    assert (info.device, info.compute_type, info.cuda_available) == ("cpu", "int8", False)


def test_detect_cuda_when_device_and_runtime_ok(monkeypatch):
    monkeypatch.setattr(hs, "ctranslate2", FakeCTranslate2(count=1))
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: True)
    info = hs.detect()
    assert (info.device, info.compute_type, info.cuda_available) == ("cuda", "float16", True)


def test_detect_cpu_when_runtime_dlls_missing(monkeypatch):
    # Device reported but DLLs not loadable -> must NOT pick cuda (segfault risk)
    monkeypatch.setattr(hs, "ctranslate2", FakeCTranslate2(count=1))
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: False)
    info = hs.detect()
    assert info.device == "cpu"
    assert info.cuda_available is False


def test_detect_cpu_when_ctranslate2_raises(monkeypatch):
    monkeypatch.setattr(hs, "ctranslate2", FakeCTranslate2(count=1, raises=True))
    info = hs.detect()
    assert (info.device, info.compute_type, info.cuda_available) == ("cpu", "int8", False)


def test_resolve_auto_delegates_to_detect(monkeypatch):
    monkeypatch.setattr(hs, "ctranslate2", FakeCTranslate2(count=1))
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: True)
    info = hs.resolve("auto")
    assert info.device == "cuda"


def test_resolve_cuda_override(monkeypatch):
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: True)
    info = hs.resolve("cuda")
    assert (info.device, info.compute_type, info.cuda_available) == ("cuda", "float16", True)


def test_resolve_cuda_override_falls_back_when_runtime_missing(monkeypatch):
    monkeypatch.setattr(hs, "_cuda_runtime_available", lambda: False)
    info = hs.resolve("cuda")
    assert info.device == "cpu"
    assert info.cuda_available is False


def test_resolve_cpu_override():
    info = hs.resolve("cpu")
    assert (info.device, info.compute_type, info.cuda_available) == ("cpu", "int8", False)


def test_resolve_unknown_value_falls_back_to_cpu():
    info = hs.resolve("banana")
    assert info.device == "cpu"


# ---------------------------------------------------- _cuda_runtime_available

class FakeGlob:
    """Patches the function-local `import glob` used by _cuda_runtime_available."""

    def __init__(self, found=True, fail_load_on=None):
        self._found = found
        self._fail_load_on = fail_load_on or set()

    def glob(self, pattern):
        if not self._found:
            return []
        name = pattern.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].replace(".dll", "")
        if name in self._fail_load_on:
            return []  # pattern missing entirely
        return [f"C:/dlls/{name}.dll"]

    def __getattr__(self, name):
        return self.glob


class FakeCDLL:
    def __init__(self, fail_load_on):
        self._fail_load_on = fail_load_on

    def __call__(self, path):
        if any(tag in path for tag in self._fail_load_on):
            raise OSError(f"cannot load {path}")
        return object()


def _patch_dll_search(monkeypatch, tmp_path, found=True, fail_load_on=None):
    # The autouse fixture stubs _cuda_runtime_available to False for the
    # detect() tests; restore the real implementation here.
    monkeypatch.setattr(hs, "_cuda_runtime_available", _REAL_CUDA_RUNTIME)
    monkeypatch.setitem(sys.modules, "glob", FakeGlob(found=found, fail_load_on=fail_load_on))
    monkeypatch.setitem(sys.modules, "ctypes", SimpleNamespace(CDLL=FakeCDLL(fail_load_on or set())))
    monkeypatch.setenv("CUDA_PATH", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))


def test_cuda_runtime_missing_dlls(monkeypatch, tmp_path):
    _patch_dll_search(monkeypatch, tmp_path, found=False)
    assert hs._cuda_runtime_available() is False


def test_cuda_runtime_dll_load_failure(monkeypatch, tmp_path):
    _patch_dll_search(monkeypatch, tmp_path, found=True, fail_load_on={"cublas64"})
    assert hs._cuda_runtime_available() is False


def test_cuda_runtime_all_dlls_ok(monkeypatch, tmp_path):
    _patch_dll_search(monkeypatch, tmp_path, found=True)
    assert hs._cuda_runtime_available() is True


def test_required_dlls_cover_full_stack():
    # All four must be present: cudart, cublas, cublasLt, cudnn
    assert hs.REQUIRED_CUDA_DLLS == ["cudart64_*", "cublas64_*", "cublasLt64_*", "cudnn64_*"]
