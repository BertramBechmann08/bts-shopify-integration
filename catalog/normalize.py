import re


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_sizes(text: str) -> str:
    return re.sub(r"(\d+)\s*ml\b", r"\1 ml", text, flags=re.IGNORECASE)


def title_case_known_phrase(text: str, phrase: str, replacement: str) -> str:
    return re.sub(re.escape(phrase), replacement, text, flags=re.IGNORECASE)


def normalize_perfume_terms(text: str) -> str:
    replacements = [
        (r"\bEau De Perfume\b", "Eau de Parfum"),
        (r"\bEau De Parfum\b", "Eau de Parfum"),
        (r"\bEau De Toilette\b", "Eau de Toilette"),
        (r"\bEdp\b", "Eau de Parfum"),
        (r"\bEdt\b", "Eau de Toilette"),
        (r"\bSpray\b", ""),
    ]

    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    text = normalize_sizes(text)
    text = normalize_spaces(text)
    return text


def clean_product_title(source_title: str) -> str:
    title = normalize_perfume_terms(source_title)

    known_phrases = [
        ("Eau De Rochas", "Eau de Rochas"),
        ("Eau De Rochas Homme", "Eau de Rochas Homme"),
        ("Eau De Toilette", "Eau de Toilette"),
        ("Eau De Parfum", "Eau de Parfum"),
        ("Lempicka Homme", "Lempicka Homme"),
    ]

    for phrase, replacement in known_phrases:
        title = title_case_known_phrase(title, phrase, replacement)

    # General cleanup
    title = re.sub(r"\bPerfume\b", "Parfum", title, flags=re.IGNORECASE)

    title = normalize_sizes(title)
    title = normalize_spaces(title)
    return title