#!/usr/bin/env python3
"""Deterministic scanner for the bundled Xianyu RAG word lists."""
import argparse
import json
import re
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1] / "references" / "xianyu-wordlists.md"
SECTIONS = ("商品违禁词", "商品版权词", "平台盗版违规词")

def load_words():
    text = LIBRARY.read_text(encoding="utf-8")
    result = {}
    for i, section in enumerate(SECTIONS):
        start = text.find("## " + section)
        end = min((text.find("## ", start + 3) if text.find("## ", start + 3) >= 0 else len(text)), len(text))
        block = text[start:end]
        result[section] = sorted(set(re.findall(r"`([^`]+)`", block)), key=lambda x: (-len(x), x))
    return result

def scan(content):
    hits = []
    for category, words in load_words().items():
        for word in words:
            # Single-character entries create unacceptable Chinese substring false positives.
            if len(word) < 2:
                continue
            for match in re.finditer(re.escape(word), content, flags=re.IGNORECASE):
                hits.append({"word": word, "category": category,
                             "start": match.start(), "end": match.end()})
    return sorted(hits, key=lambda x: (x["start"], -len(x["word"]), x["category"]))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    hits = scan(args.text)
    print(json.dumps({"matched": bool(hits), "count": len(hits), "hits": hits}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
