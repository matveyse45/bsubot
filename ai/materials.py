"""Учебные материалы: поиск по .txt/.md из data/materials (без внешних зависимостей).

Простое сопоставление по ключевым словам (первые 5 букв слова). Подходит для старта;
позже можно заменить на векторный поиск, сохранив интерфейс search()/sources().
"""
import re
from pathlib import Path

MATERIALS_DIR = Path(__file__).resolve().parent.parent / "data" / "materials"
_chunks: list[dict] = []


def _tokens(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яёa-z0-9_+#]{3,}", text.lower())}


def _add(source: str, text: str) -> None:
    _chunks.append({"source": source, "text": text, "tokens": _tokens(text)})


def load() -> None:
    _chunks.clear()
    if not MATERIALS_DIR.is_dir():
        return
    for path in sorted(MATERIALS_DIR.rglob("*")):
        if path.suffix.lower() not in (".txt", ".md") or path.name.startswith("_"):
            continue
        buf = ""
        for para in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="ignore")):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) > 900:
                _add(path.name, buf)
                buf = ""
            buf = f"{buf}\n\n{para}".strip()
        if buf:
            _add(path.name, buf)


def sources() -> list[str]:
    return sorted({c["source"] for c in _chunks})


def search(query: str, k: int = 3) -> list[dict]:
    q = _tokens(query)
    if not q:
        return []
    need = min(2, len(q))
    scored = [(len(q & c["tokens"]), c) for c in _chunks]
    scored = [(s, c) for s, c in scored if s >= need]
    scored.sort(key=lambda x: -x[0])
    return [{"source": c["source"], "text": c["text"]} for _, c in scored[:k]]


load()
