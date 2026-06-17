"""Match detected theme markers to textbook_toc leaf entries."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.pipeline.theme_stream.detector import ThemeMarker


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _norm_num(s: str) -> str:
    return s.replace("–", "-").replace("—", "-").strip()


class TocMatcher:
    def __init__(self, leaves: list[dict]) -> None:
        self.leaves = leaves
        self._by_number: dict[str, list[dict]] = {}
        self._repetition: list[dict] = []
        self._self_tests: list[dict] = []
        for leaf in leaves:
            num = _norm_num(str(leaf.get("number") or ""))
            title = _norm(leaf.get("title") or "")
            parent = str(leaf.get("parent_number") or "")
            if num.startswith("тест") or "проверьте" in title:
                self._self_tests.append(leaf)
            elif parent == "Повторение":
                self._repetition.append(leaf)
            self._by_number.setdefault(num, []).append(leaf)

    def match(self, marker: ThemeMarker) -> tuple[dict | None, float]:
        """Return (toc_entry, confidence)."""
        if marker.kind == "self_test":
            return self._match_self_test(marker)
        if marker.kind == "repetition":
            return self._match_repetition(marker)
        return self._match_theme(marker)

    def _match_repetition(self, marker: ThemeMarker) -> tuple[dict | None, float]:
        num = marker.number
        for leaf in self._repetition:
            n = _norm_num(str(leaf.get("number") or ""))
            if n == num or n.startswith(f"{num}-") or n.startswith(f"{num}–"):
                return leaf, 0.95
        # fuzzy title
        mt = _norm(marker.title)
        best: dict | None = None
        best_sc = 0.0
        for leaf in self._repetition:
            sc = SequenceMatcher(None, mt, _norm(leaf.get("title") or "")).ratio()
            if sc > best_sc:
                best_sc = sc
                best = leaf
        if best and best_sc >= 0.45:
            return best, best_sc
        return None, 0.0

    def _match_self_test(self, marker: ThemeMarker) -> tuple[dict | None, float]:
        mn = _norm(marker.number)
        for leaf in self._self_tests:
            ln = _norm_num(str(leaf.get("number") or ""))
            if ln == mn or mn in ln or ln in mn:
                return leaf, 0.92
        # any self-test leaf without roman match — pick by order if single
        if len(self._self_tests) == 1:
            return self._self_tests[0], 0.7
        for leaf in self._self_tests:
            if "проверьте" in _norm(leaf.get("title") or ""):
                return leaf, 0.85
        return None, 0.0

    def _match_theme(self, marker: ThemeMarker) -> tuple[dict | None, float]:
        num = _norm_num(marker.number)
        candidates = self._by_number.get(num, [])
        if len(candidates) == 1:
            return candidates[0], 0.95
        if candidates:
            mt = _norm(marker.title)
            best = max(
                candidates,
                key=lambda c: SequenceMatcher(
                    None, mt, _norm(c.get("title") or "")
                ).ratio(),
            )
            sc = SequenceMatcher(None, mt, _norm(best.get("title") or "")).ratio()
            return best, max(sc, 0.75)

        # range overlap: marker "1-2" vs toc "1–7" — prefer exact theme keys
        mt = _norm(marker.title)
        best: dict | None = None
        best_sc = 0.0
        for leaf in self.leaves:
            if leaf in self._repetition or leaf in self._self_tests:
                continue
            ln = _norm_num(str(leaf.get("number") or ""))
            title_sc = SequenceMatcher(None, mt, _norm(leaf.get("title") or "")).ratio()
            num_sc = 0.9 if ln == num else 0.0
            sc = max(title_sc, num_sc)
            if sc > best_sc:
                best_sc = sc
                best = leaf
        if best and best_sc >= 0.55:
            return best, best_sc
        return None, 0.0
