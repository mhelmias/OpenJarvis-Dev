import importlib.machinery
import importlib.util
import json
import pathlib
import re
import time
import types

import pytest

HELPER = pathlib.Path(__file__).resolve().parent.parent / "helper" / "jarvis-panel-helper"
KEY = "nvapi-RAHASIA-1234567890"


def load_helper():
    loader = importlib.machinery.SourceFileLoader("panel_helper", str(HELPER))
    spec = importlib.util.spec_from_loader("panel_helper", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Failed(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def make_jm(tmp_path, saved=True):
    keys = {"KEY_NVIDIA": "nvapi-tersimpan-123"} if saved else {}
    calls = []

    def fetch_models(provider, key):
        calls.append(("fetch", provider))
        if key == "nvapi-ditolak-12345":
            raise Failed("HTTP 401", code=401)
        return ["a/ok", "b/lambat", "c/lain"]

    def test_model(provider, key, model):
        calls.append(("test", model))
        print(f"Menguji {model} ...")
        if model == "x/rusak":
            raise Failed("HTTP 404", code=404)
        return model != "c/lain"

    def scan(provider, key, models):
        calls.append(("scan", tuple(models)))
        return {"a/ok": ("ok", "bisa, 1 detik"), "b/lambat": ("error", "terlalu lama, tidak menjawab")}

    jm = types.SimpleNamespace(
        PROVIDERS={"nvidia": {"label": "NVIDIA build", "engine": "nim", "suggested": ["a/ok", "b/lambat", "z/tidak-ada"]},
                   "openai": {"label": "OpenAI", "engine": "cloud", "suggested": []}},
        ORDER=["nvidia", "openai"], KEYS="keys", ACTIVE="active", SERVICE="openjarvis.service",
        MODEL_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$"),
        KEY_RE=re.compile(r"^[A-Za-z0-9._~+/=:-]{10,400}$"),
        Failed=Failed,
        reason=lambda exc: {401: "kunci ditolak", 404: "tidak tersedia untuk akun ini"}.get(exc.code, str(exc)),
        read_env=lambda path: dict(keys) if path == "keys" else {"JARVIS_ENGINE": "nim"},
        current=lambda: ("nvidia", "a/ok"),
        fetch_models=fetch_models, test_model=test_model, scan=scan,
        save_key=lambda provider, key: (calls.append(("save", provider)), keys.__setitem__(f"KEY_{provider.upper()}", key)),
        apply=lambda provider, key, model: calls.append(("apply", model)),
    )
    return jm, calls


@pytest.fixture
def helper(tmp_path, monkeypatch):
    module = load_helper()
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(module, "SPOOL", str(spool))
    monkeypatch.setattr(module, "service_state", lambda jm: "active")
    return module


def test_use_tests_then_applies(helper, tmp_path):
    jm, calls = make_jm(tmp_path)
    out = helper.handle(jm, {"action": "use", "provider": "nvidia", "model": "a/ok"}, {})
    assert out["ok"] and "a/ok" in out["message"] and "Menguji a/ok" in out["log"]
    assert calls == [("test", "a/ok"), ("apply", "a/ok")]


@pytest.mark.parametrize("model, expected", [("x/rusak", "tidak tersedia"), ("c/lain", "tidak memakai tool"),
                                             ("a; reboot", "tidak valid")])
def test_use_does_not_apply_bad_models(helper, tmp_path, model, expected):
    jm, calls = make_jm(tmp_path)
    out = helper.handle(jm, {"action": "use", "provider": "nvidia", "model": model}, {})
    assert not out["ok"] and expected in out["message"]
    assert ("apply", model) not in calls


def test_key_is_checked_saved_and_never_returned(helper, tmp_path):
    jm, calls = make_jm(tmp_path, saved=False)
    cache = {}
    assert not helper.handle(jm, {"action": "key", "provider": "nvidia", "key": "nvapi-ditolak-12345"}, cache)["ok"]
    assert not helper.handle(jm, {"action": "key", "provider": "nvidia", "key": "ada spasi"}, cache)["ok"]
    out = helper.handle(jm, {"action": "key", "provider": "nvidia", "key": KEY}, cache)
    assert out["ok"] and KEY not in json.dumps(out)
    assert ("save", "nvidia") in calls and cache["nvidia"]["ids"] == ["a/ok", "b/lambat", "c/lain"]


def test_models_scan_and_guards(helper, tmp_path):
    jm, calls = make_jm(tmp_path)
    cache = {}
    assert helper.handle(jm, {"action": "models", "provider": "nvidia"}, cache)["ok"]
    out = helper.handle(jm, {"action": "scan", "provider": "nvidia"}, cache)
    assert out["ok"] and "1 dari 2" in out["message"]
    assert ("scan", ("a/ok", "b/lambat")) in calls
    assert not helper.handle(jm, {"action": "models", "provider": "openai"}, cache)["ok"]  # belum ada kunci
    assert not helper.handle(jm, {"action": "use", "provider": "evil", "model": "a/ok"}, cache)["ok"]
    assert not helper.handle(jm, {"action": "shell", "provider": "nvidia"}, cache)["ok"]


def test_main_end_to_end(helper, tmp_path, monkeypatch):
    jm, calls = make_jm(tmp_path, saved=False)
    monkeypatch.setattr(helper, "load_jarvis_model", lambda: jm)
    spool = pathlib.Path(helper.SPOOL)
    (spool / "request.json").write_text(json.dumps(
        {"id": "1", "action": "key", "provider": "nvidia", "key": KEY, "at": time.time()}))
    assert helper.main() == 0
    assert not (spool / "request.json").exists() and not (spool / "running.json").exists()
    result = json.loads((spool / "result.json").read_text())
    status = json.loads((spool / "status.json").read_text())
    assert result["ok"] and result["action"] == "key"
    assert status["providers"][0]["has_key"] is True and status["model"] == "a/ok"
    for name in ("result.json", "status.json"):
        assert KEY not in (spool / name).read_text()


def test_main_ignores_stale_request(helper, tmp_path, monkeypatch):
    jm, calls = make_jm(tmp_path)
    monkeypatch.setattr(helper, "load_jarvis_model", lambda: jm)
    spool = pathlib.Path(helper.SPOOL)
    (spool / "request.json").write_text(json.dumps(
        {"id": "2", "action": "use", "provider": "nvidia", "model": "a/ok", "at": time.time() - 3600}))
    helper.main()
    assert "kedaluwarsa" in json.loads((spool / "result.json").read_text())["message"]
    assert calls == []
