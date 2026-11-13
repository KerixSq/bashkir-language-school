import re
import secrets
import unicodedata
from collections import Counter

JOIN_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def valid_nickname(value: str) -> bool:
    return (
        3 <= len(value) <= 20
        and value == value.strip()
        and all(char.isalpha() or char.isdecimal() or char in ' _-' for char in value)
        and any(char.isalpha() or char.isdecimal() for char in value)
    )


def new_join_code(length: int = 8) -> str:
    if not 6 <= length <= 8:
        raise ValueError('Длина кода должна быть 6–8 символов')
    return ''.join(secrets.choice(JOIN_ALPHABET) for _ in range(length))


def normalize_translation(value: str | None) -> str:
    text = re.sub(r'\s+', ' ', value or '').strip()
    text = text.strip(' «»„“”')
    while text and unicodedata.category(text[0]).startswith('P'):
        text = text[1:]
    while text and unicodedata.category(text[-1]).startswith('P'):
        text = text[:-1]
    return text.strip().lower().replace('ё', 'е')


def display_translation(leader: str, automatic: str, corrections: list[str]) -> str:
    if leader == normalize_translation(automatic):
        return automatic
    counts = Counter(text.strip() for text in corrections if normalize_translation(text) == leader)
    if not counts:
        raise ValueError('Нет исходного текста для победившего исправления')
    return sorted(counts, key=lambda text: (-counts[text], text))[0]


def split_long(text: str, limit: int = 300) -> list[str]:
    parts = []
    buffer = ''
    for word in text.split():
        if len(word) > limit:
            raise ValueError('Слово длиннее 300 символов')
        candidate = (buffer + ' ' + word).strip()
        if len(candidate) > limit:
            parts.append(buffer)
            buffer = word
        else:
            buffer = candidate
    if buffer:
        parts.append(buffer)
    return parts


def split_fragments(text: str) -> list[str]:
    chunks = re.split(r'(?<=[.!?…])\s+|\n\s*\n', text.replace('\r', ''))
    items = []
    for chunk in chunks:
        cleaned = re.sub(r'\s+', ' ', chunk).strip()
        if cleaned:
            items.extend(split_long(cleaned))

    merged = []
    buffer = ''
    for item in items:
        if buffer and len(buffer) >= 20:
            merged.append(buffer)
            buffer = ''
        if buffer and len(buffer) + len(item) + 1 > 300:
            merged.append(buffer)
            buffer = ''
        buffer = (buffer + ' ' + item).strip()
    if buffer:
        if len(buffer) < 20 and merged and len(merged[-1]) + len(buffer) + 1 <= 300:
            merged[-1] += ' ' + buffer
            buffer = ''
        elif len(buffer) < 20 and merged:
            words = merged[-1].split()
            tail = buffer.split()
            while len(' '.join(tail)) < 20 and len(words) > 1:
                tail.insert(0, words.pop())
            if len(' '.join(words)) >= 20:
                merged[-1] = ' '.join(words)
                buffer = ' '.join(tail)
        if buffer:
            merged.append(buffer)
    # Отказываться от короткого остатка без предупреждения нельзя.
    invalid = [part for part in merged if not 20 <= len(part) <= 300]
    if invalid:
        raise ValueError('Не удалось разбить текст без потери фрагмента короче 20 символов')
    return merged


def vote_weight(caught: int, missed: int, step: float = 0.1) -> float:
    return round(max(0.5, min(1.5, 1 + step * (caught - missed))), 2)


def secret_hash(secret: str) -> str:
    import hashlib

    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def new_api_key() -> str:
    return 'bsk_' + secrets.token_urlsafe(32)


def levenshtein(first: str, second: str) -> int:
    if len(first) < len(second):
        first, second = second, first
    previous = list(range(len(second) + 1))
    for index, char in enumerate(first, 1):
        row = [index]
        for position, other in enumerate(second, 1):
            row.append(
                min(row[-1] + 1, previous[position] + 1, previous[position - 1] + (char != other))
            )
        previous = row
    return previous[-1]


def chapters(text: str, default: str, pattern: str | None) -> list[tuple[str, str]]:
    if not pattern:
        return [(default, text)]
    expression = re.compile(pattern, re.MULTILINE)
    matches = list(expression.finditer(text))
    if not matches:
        return [(default, text)]
    items = []
    if text[: matches[0].start()].strip():
        items.append((default, text[: matches[0].start()]))
    for index, match in enumerate(matches):
        title = match.group(1) if match.lastindex else match.group(0)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        items.append((title.strip()[:120], text[match.end() : end]))
    return items
