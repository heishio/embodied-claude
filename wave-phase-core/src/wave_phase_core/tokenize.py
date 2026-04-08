"""Tokenization using sudachipy."""
import sudachipy

_tok = sudachipy.Dictionary().create()


def tokenize_sent(text: str) -> list[dict]:
    return [
        {
            'surface': m.surface(),
            'lemma': m.dictionary_form(),
            'reading': m.reading_form(),
            'pos': m.part_of_speech()[0],
        }
        for m in _tok.tokenize(text, sudachipy.Tokenizer.SplitMode.C)
        if m.part_of_speech()[0] not in ('補助記号', '空白')
    ]
