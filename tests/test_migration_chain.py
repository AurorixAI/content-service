"""Цепочка миграций должна быть целой.

Этот тест существует из-за B25: продовая база стояла на ревизии
`h9b0c1d2e3f4`, файла с которой не было ни в одной ветке. Обнаружилось это
только при сверке с выгрузкой прода — то есть спустя недели, и ценой того, что
автодеплой упал бы на первом же push в `main`.

Проверить цепочку можно было всё это время одной командой.
"""
import pathlib
import re

VERSIONS = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"

# Часть файлов объявляет ревизию с аннотацией (`revision: str = "..."`),
# часть без неё — регулярка должна принимать оба вида.
_REV_RE = re.compile(r"^revision(?:\s*:\s*\w+)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
_DOWN_RE = re.compile(
    r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M
)


def _chain():
    revs = {}
    for path in VERSIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        m = _REV_RE.search(text)
        assert m, f"{path.name}: не найден revision"
        down = _DOWN_RE.search(text)
        revs[m.group(1)] = (down.group(1) if down else None, path.name)
    return revs


class TestMigrationChain:
    def test_every_parent_exists(self):
        """Ссылка на несуществующую ревизию — то, на чём падает деплой."""
        revs = _chain()
        missing = [
            (rev, down, name)
            for rev, (down, name) in revs.items()
            if down is not None and down not in revs
        ]
        assert not missing, f"ревизии-сироты: {missing}"

    def test_single_head(self):
        """Две головы означают, что `upgrade head` не знает, куда идти."""
        revs = _chain()
        parents = {down for down, _ in revs.values() if down}
        heads = sorted(set(revs) - parents)
        assert len(heads) == 1, f"голов должно быть ровно одна, найдено: {heads}"

    def test_single_base(self):
        revs = _chain()
        bases = sorted(r for r, (down, _) in revs.items() if down is None)
        assert len(bases) == 1, f"баз должно быть ровно одна, найдено: {bases}"

    def test_no_cycles(self):
        revs = _chain()
        for start in revs:
            seen, cur = set(), start
            while cur is not None:
                assert cur not in seen, f"цикл через {cur}"
                seen.add(cur)
                cur = revs[cur][0] if cur in revs else None

    def test_prod_revision_is_reachable(self):
        """Ревизия, на которой стоит прод, обязана быть в цепочке.

        Значение взято из выгрузки `algo_content` от 2026-09-01. Пока прод не
        передвинулся дальше, потеря этого файла снова обрушит деплой.
        """
        assert "h9b0c1d2e3f4" in _chain(), (
            "ревизия продовой базы отсутствует — `alembic upgrade head` на проде упадёт"
        )
