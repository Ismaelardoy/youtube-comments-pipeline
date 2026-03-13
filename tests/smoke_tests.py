"""Smoke tests for the refactored src/ package.
Run from the project root: .venv\Scripts\python.exe tests\smoke_tests.py
"""
import os
import sys

# Ensure the project root (parent of this file) is on the path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# ── text_cleaner ──────────────────────────────────────────────────────────────
from src.utils.text_cleaner import clean_comment_text, is_meaningful

r1 = clean_comment_text("<b>Hello</b> world https://t.co/abc")
assert r1 == "Hello world", f"Got: {r1!r}"

r2 = clean_comment_text("")
assert r2 == "", f"Got: {r2!r}"

r3 = clean_comment_text("  check &amp; mate  ")
assert r3 == "check & mate", f"Got: {r3!r}"

assert is_meaningful("ok") is False,  "2-char string should NOT be meaningful"
assert is_meaningful("hey!") is True, "4-char string should be meaningful"

print("text_cleaner .............. PASSED")

# ── file_naming ───────────────────────────────────────────────────────────────
from src.utils.file_naming import generate_filename

nm = generate_filename("politics debate", ["abc", "xyz"], "20250101120000")
assert "megablob" in nm,        f"Expected megablob prefix, got: {nm}"
assert "politics_debate" in nm, f"Expected sanitised theme, got: {nm}"

ns = generate_filename(None, ["dQw4w9WgXcQ"], "20250101120000")
assert ns == "comments_dQw4w9WgXcQ_20250101120000.json", f"Got: {ns}"

print("file_naming ............... PASSED")

# ── Settings ──────────────────────────────────────────────────────────────────
os.environ["YOUTUBE_API_KEY"] = "test-key"
from src.config.settings import load_settings

s = load_settings()
assert s.youtube_api_key == "test-key"
assert s.global_comment_limit == 10000
assert s.total_requests == 2
assert len(s.themes) == 14

print("Settings .................. PASSED")
print()
print("All smoke tests PASSED.")
