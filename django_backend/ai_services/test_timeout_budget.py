import time

import pytest

from ai_services import gemini_ai


class TestCallWithTimeout:
    def test_returns_value_when_fast(self):
        assert gemini_ai._call_with_timeout(lambda: 42, 2) == 42

    def test_propagates_worker_exception(self):
        def boom():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            gemini_ai._call_with_timeout(boom, 2)

    def test_raises_timeout_when_slow(self):
        start = time.monotonic()
        with pytest.raises(gemini_ai.TimeoutError):
            gemini_ai._call_with_timeout(lambda: time.sleep(5), 0.2)
        assert time.monotonic() - start < 2


class TestGenerateContentBudget:
    def test_fallbacks_stop_at_total_budget(self, monkeypatch):
        calls = []

        class FakeModels:
            def generate_content(self, model, contents):
                calls.append(model)
                time.sleep(1)
                return None

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(gemini_ai, "get_client", lambda: FakeClient())
        monkeypatch.setattr(
            gemini_ai,
            "_models_for_current_attempt",
            lambda: ["m1", "m2", "m3", "m4", "m5"],
        )
        monkeypatch.setattr(gemini_ai, "GEMINI_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(gemini_ai, "AI_TOTAL_TIMEOUT_SECONDS", 0.5)

        start = time.monotonic()
        with pytest.raises(gemini_ai.GeminiAPIError):
            gemini_ai._generate_content("prompt")
        elapsed = time.monotonic() - start

        assert elapsed < 1.5
        assert 0 < len(calls) < 5

    def test_budget_exhaustion_reports_504(self, monkeypatch):
        class FakeModels:
            def generate_content(self, model, contents):
                time.sleep(1)

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(gemini_ai, "get_client", lambda: FakeClient())
        monkeypatch.setattr(
            gemini_ai,
            "_models_for_current_attempt",
            lambda: ["m1", "m2"],
        )
        monkeypatch.setattr(gemini_ai, "GEMINI_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(gemini_ai, "AI_TOTAL_TIMEOUT_SECONDS", 0.3)

        with pytest.raises(gemini_ai.GeminiAPIError) as excinfo:
            gemini_ai._generate_content("prompt")

        assert excinfo.value.status_code == 504


class TestProjectFilesText:
    def test_caps_total_size_and_notes_truncation(self):
        files = {f"src/file{i}.js": "x" * 5000 for i in range(40)}
        text = gemini_ai._project_files_text(files)

        assert len(text) <= gemini_ai.CHAT_FILES_CHAR_BUDGET + 1000
        assert "omitted" in text

    def test_small_projects_are_untouched(self):
        files = {"app.py": "print('hi')"}
        text = gemini_ai._project_files_text(files)
        assert text == "=== app.py ===\nprint('hi')"
