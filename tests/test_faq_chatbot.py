"""Tests for faq_chatbot.load_faq function."""

import os
import stat

import pytest

from faq_chatbot import load_faq, MAX_FAQ_LENGTH


class TestLoadFaqHappyPath:
    def test_loads_valid_faq_content(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("# FAQ\n\nQ: What is X?\nA: X is Y.", encoding="utf-8")
        result = load_faq(str(faq))
        assert result == "# FAQ\n\nQ: What is X?\nA: X is Y."

    def test_preserves_exact_content(self, tmp_path):
        content = "Line 1\n\nLine 2\n\ttabbed\n"
        faq = tmp_path / "faq.md"
        faq.write_text(content, encoding="utf-8")
        result = load_faq(str(faq))
        assert result == content


class TestLoadFaqFileNotFound:
    def test_exits_when_file_missing(self, tmp_path):
        missing = str(tmp_path / "nonexistent.md")
        with pytest.raises(SystemExit) as exc_info:
            load_faq(missing)
        assert exc_info.value.code == 1

    def test_prints_error_when_file_missing(self, tmp_path, capsys):
        missing = str(tmp_path / "nonexistent.md")
        with pytest.raises(SystemExit):
            load_faq(missing)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()


class TestLoadFaqEmptyContent:
    def test_exits_when_file_empty(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            load_faq(str(faq))
        assert exc_info.value.code == 1

    def test_exits_when_file_whitespace_only(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("   \n\t\n  ", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            load_faq(str(faq))
        assert exc_info.value.code == 1

    def test_prints_error_when_file_empty(self, tmp_path, capsys):
        faq = tmp_path / "faq.md"
        faq.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_faq(str(faq))
        captured = capsys.readouterr()
        assert "empty" in captured.out.lower() or "whitespace" in captured.out.lower()


class TestLoadFaqPermissionError:
    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_exits_when_file_unreadable(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("content", encoding="utf-8")
        faq.chmod(0o000)
        try:
            with pytest.raises(SystemExit) as exc_info:
                load_faq(str(faq))
            assert exc_info.value.code == 1
        finally:
            faq.chmod(stat.S_IRUSR | stat.S_IWUSR)

    @pytest.mark.skipif(os.name == "nt", reason="Unix permission model")
    def test_prints_error_when_file_unreadable(self, tmp_path, capsys):
        faq = tmp_path / "faq.md"
        faq.write_text("content", encoding="utf-8")
        faq.chmod(0o000)
        try:
            with pytest.raises(SystemExit):
                load_faq(str(faq))
            captured = capsys.readouterr()
            assert "could not read" in captured.out.lower()
        finally:
            faq.chmod(stat.S_IRUSR | stat.S_IWUSR)


class TestLoadFaqSizeLimit:
    def test_exits_when_file_too_large(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("x" * (MAX_FAQ_LENGTH + 1), encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            load_faq(str(faq))
        assert exc_info.value.code == 1

    def test_accepts_file_at_exact_limit(self, tmp_path):
        faq = tmp_path / "faq.md"
        faq.write_text("x" * MAX_FAQ_LENGTH, encoding="utf-8")
        result = load_faq(str(faq))
        assert len(result) == MAX_FAQ_LENGTH

    def test_prints_error_when_file_too_large(self, tmp_path, capsys):
        faq = tmp_path / "faq.md"
        faq.write_text("x" * (MAX_FAQ_LENGTH + 1), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_faq(str(faq))
        captured = capsys.readouterr()
        assert "too large" in captured.out.lower() or "exceeds" in captured.out.lower()


# --- Tests for load_api_key (Task 1.2) ---

from faq_chatbot import load_api_key


class TestLoadApiKeyMissingEnvFile:
    def test_exits_when_env_file_missing(self, tmp_path, monkeypatch):
        """Should exit with code 1 when .env file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            load_api_key()
        assert exc_info.value.code == 1

    def test_prints_error_when_env_file_missing(self, tmp_path, monkeypatch, capsys):
        """Should print error message about missing .env file."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            load_api_key()
        captured = capsys.readouterr()
        assert ".env" in captured.out
        assert "not found" in captured.out


class TestLoadApiKeyMissingVariable:
    def test_exits_when_key_not_in_env(self, tmp_path, monkeypatch):
        """Should exit with code 1 when ANTHROPIC_API_KEY is not in .env."""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_VAR=hello\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            load_api_key()
        assert exc_info.value.code == 1

    def test_prints_not_configured_message(self, tmp_path, monkeypatch, capsys):
        """Should print error about API key not configured."""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_VAR=hello\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            load_api_key()
        captured = capsys.readouterr()
        assert "ANTHROPIC_API_KEY" in captured.out
        assert "not configured" in captured.out


class TestLoadApiKeyWhitespaceOnly:
    def test_exits_when_key_is_whitespace(self, tmp_path, monkeypatch):
        """Should exit with code 1 when ANTHROPIC_API_KEY is whitespace-only."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=   \n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            load_api_key()
        assert exc_info.value.code == 1

    def test_exits_when_key_is_empty(self, tmp_path, monkeypatch):
        """Should exit with code 1 when ANTHROPIC_API_KEY is empty string."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            load_api_key()
        assert exc_info.value.code == 1


class TestLoadApiKeyValid:
    def test_returns_valid_key(self, tmp_path, monkeypatch):
        """Should return the API key when valid."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-key-123\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = load_api_key()
        assert result == "sk-ant-test-key-123"

    def test_returns_key_with_special_characters(self, tmp_path, monkeypatch):
        """Should handle API keys with various characters."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-api03-abcDEF123_xyz\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = load_api_key()
        assert result == "sk-ant-api03-abcDEF123_xyz"


# --- Tests for trim_history (Task 4.1) ---

from faq_chatbot import trim_history


class TestTrimHistoryNoTrimNeeded:
    def test_returns_empty_history_unchanged(self):
        """Empty history should be returned as-is."""
        assert trim_history([]) == []

    def test_returns_single_pair_unchanged_with_default(self):
        """A single pair (2 messages) is within default keep_latest=2."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = trim_history(history)
        assert result == history

    def test_returns_two_pairs_unchanged_with_default(self):
        """Two pairs exactly matches the default keep_latest=2."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]
        result = trim_history(history)
        assert result == history


class TestTrimHistoryTrims:
    def test_trims_oldest_pair_keeping_two(self):
        """Three pairs trimmed to keep_latest=2 removes the oldest pair."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]
        result = trim_history(history)
        assert result == [
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]

    def test_trims_many_pairs_keeping_two(self):
        """Five pairs trimmed to default 2 keeps only the last two pairs."""
        history = [
            {"role": "user", "content": f"Q{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"A{i}"}
            for i in range(10)
        ]
        result = trim_history(history)
        assert len(result) == 4
        assert result == history[-4:]

    def test_custom_keep_latest_one(self):
        """keep_latest=1 keeps only the most recent pair."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]
        result = trim_history(history, keep_latest=1)
        assert result == [
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]

    def test_custom_keep_latest_three(self):
        """keep_latest=3 with exactly 3 pairs returns all."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]
        result = trim_history(history, keep_latest=3)
        assert result == history


class TestTrimHistoryPreservesRecency:
    def test_result_is_contiguous_suffix(self):
        """Trimmed result must be a contiguous suffix of the original."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
            {"role": "user", "content": "Q4"},
            {"role": "assistant", "content": "A4"},
        ]
        result = trim_history(history, keep_latest=2)
        # Result should be the last 4 elements
        assert result == history[-4:]
        # Verify it's truly a suffix (order preserved)
        assert result[0]["content"] == "Q3"
        assert result[-1]["content"] == "A4"
