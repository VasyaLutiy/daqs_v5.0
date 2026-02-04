import base64
import io
import os
from pathlib import Path

import pytest
from PIL import Image

import gamemaster.visual_generator as vg
from gamemaster.visual_generator import VisualGenerator


def _png_bytes(color=(255, 0, 0, 255)) -> bytes:
    """Create a tiny in-memory PNG for testing."""
    img = Image.new("RGBA", (2, 2), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, parts):
        self.parts = parts


class _FakeModels:
    def __init__(self, response):
        self._response = response

    def generate_content(self, *_, **__):
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def _make_visual_gen(tmp_path: Path, response_parts):
    """Create a VisualGenerator with a fake client and tmp cache directory."""
    # Point the cache to temp to avoid polluting repo
    vg.IMAGE_CACHE_DIR = tmp_path
    tmp_path.mkdir(parents=True, exist_ok=True)

    gen = VisualGenerator()
    gen.client = _FakeClient(_FakeResponse(response_parts))
    return gen


def _assert_valid_png(path: Path):
    with Image.open(path) as img:
        img.verify()  # type: ignore[attr-defined]


def test_as_image_pil_object(tmp_path, monkeypatch):
    """Ensure as_image() returning a PIL Image saves a valid file."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    img = Image.new("RGB", (2, 2), (0, 255, 0))

    class Part:
        def as_image(self):
            return img

    gen = _make_visual_gen(tmp_path, [Part()])
    out = gen.generate_scene_visual("desc", "Name", "Desc", "Loc")
    assert out is not None
    out_path = Path(out)
    assert out_path.exists()
    _assert_valid_png(out_path)


def test_inline_data_base64(tmp_path, monkeypatch):
    """Ensure inline_data base64 is decoded and saved."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    png_b64 = base64.b64encode(_png_bytes()).decode("utf-8")

    class InlineData:
        def __init__(self, data):
            self.data = data

    class Part:
        def __init__(self, data):
            self.inline_data = InlineData(data)

    gen = _make_visual_gen(tmp_path, [Part(png_b64)])
    out = gen.generate_scene_visual("desc", "Name", "Desc", "Loc")
    assert out is not None
    out_path = Path(out)
    assert out_path.exists()
    _assert_valid_png(out_path)


def test_invalid_cache_is_replaced(tmp_path, monkeypatch):
    """If a cached file is invalid, it should be regenerated with valid content."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    # Prepare an invalid cache file
    target = tmp_path / "scene_invalid.png"
    target.write_text("not an image")

    # Fake response with valid inline image
    png_bytes = _png_bytes((0, 0, 255, 255))
    png_b64 = base64.b64encode(png_bytes).decode("utf-8")

    class InlineData:
        def __init__(self, data):
            self.data = data

    class Part:
        def __init__(self, data):
            self.inline_data = InlineData(data)

    gen = _make_visual_gen(tmp_path, [Part(png_b64)])
    # Call internal helper directly to target our prewritten file
    out = gen._generate_and_save(target, "prompt")
    assert out is not None
    out_path = Path(out)
    assert out_path.exists()
    _assert_valid_png(out_path)
    # Ensure the original invalid content was replaced
    with open(out_path, "rb") as f:
        assert b"not an image" not in f.read()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set; live Gemini call skipped")
def test_live_gemini_image_generation(tmp_path, monkeypatch):
    """
    Live test that hits the real Gemini image model.
    - Requires GEMINI_API_KEY in env.
    - Uses a tiny prompt and writes to a temp cache.
    """
    # Point cache to temp to avoid repo writes
    vg.IMAGE_CACHE_DIR = tmp_path
    tmp_path.mkdir(parents=True, exist_ok=True)

    gen = VisualGenerator()
    # If client is None despite key, skip
    if gen.client is None:
        pytest.skip("VisualGenerator has no client; check GEMINI_API_KEY")

    out = gen.generate_scene_visual(
        description="A small cozy tavern corner with a single candle on the table.",
        npc_name="Test NPC",
        npc_desc="Simple barkeep",
        location_name="Test Tavern",
    )
    assert out is not None, "Generation returned no path"
    out_path = Path(out)
    assert out_path.exists(), "Image file not created"
    _assert_valid_png(out_path)
