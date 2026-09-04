"""Фолбэк на текстовый слой PDF, когда Vision не распознал страницу.

Регрессия: раньше на этом месте подставлялась пустая строка — страница молча
исчезала из книги. На textzadachi5 так терялась стр. 7 (задачи 4–8 и 18–21),
хотя текстовый слой по ней был.
"""

import pytest

from src.pipeline.ocr import GeminiVisionOCR


class _FakePage:
    def __init__(self, text="", raises=False):
        self._text = text
        self._raises = raises

    def get_text(self):
        if self._raises:
            raise RuntimeError("битая страница")
        return self._text


class _FakeDoc:
    def __init__(self, pages):
        self._pages = pages

    def __getitem__(self, i):
        return self._pages[i]


@pytest.fixture
def ocr(tmp_path, monkeypatch):
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "pipeline_cache_dir", str(tmp_path), raising=False)
    return GeminiVisionOCR()


#: Длиннее порога MIN_USABLE_OCR_CHARS — содержательная страница.
_REAL_PAGE = (
    "4) В соревнованиях по прыжкам в длину участвовали 18 человек, "
    "а по прыжкам в высоту — 21. Сколько человек участвовали в соревнованиях? "
    "18. а) Число 48 увеличьте на 3, полученный результат увеличьте в 3 раза."
)


class TestTextLayerFallback:
    def test_recovers_page_from_text_layer(self, ocr):
        doc = _FakeDoc([_FakePage(_REAL_PAGE)])
        assert ocr._text_layer_fallback(doc, 0) == _REAL_PAGE

    def test_empty_layer_returns_empty(self, ocr):
        # Чистый скан: текстового слоя нет — поведение как раньше.
        doc = _FakeDoc([_FakePage("")])
        assert ocr._text_layer_fallback(doc, 0) == ""

    def test_too_short_layer_is_not_used(self, ocr):
        doc = _FakeDoc([_FakePage("7")])
        assert ocr._text_layer_fallback(doc, 0) == ""

    def test_broken_page_does_not_raise(self, ocr):
        doc = _FakeDoc([_FakePage(raises=True)])
        assert ocr._text_layer_fallback(doc, 0) == ""

    def test_picks_the_right_page(self, ocr):
        doc = _FakeDoc([_FakePage("не та"), _FakePage(_REAL_PAGE)])
        assert ocr._text_layer_fallback(doc, 1) == _REAL_PAGE
