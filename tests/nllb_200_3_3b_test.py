"""NABZ-V13 isolated NLLB-200 3.3B translation test.
This file is deliberately NOT imported by production code.
It evaluates an INT8 CTranslate2 conversion of Meta's NLLB-200 3.3B.
"""
import os
import re
from pathlib import Path
import ctranslate2
from transformers import AutoTokenizer

MODEL_DIR = os.environ.get("NLLB_MODEL_DIR", "nllb-200-3.3B-ct2-int8")
SRC = "eng_Latn"
TGT = "pes_Arab"

CASES = [
    ("Major earthquake kills 25 people and injures 202 others.", {"25", "202"}),
    ("Iran says it awaits the US response to a seven-day roadmap to end the war.", {"7"}),
    ("Two hundred and two people were injured after the explosion.", set()),
    ("Four hundred people were evacuated from the area.", set()),
]

def translate(text, tokenizer, translator):
    enc = tokenizer(text, return_tensors="pt", add_special_tokens=True)
    tokens = tokenizer.convert_ids_to_tokens(enc["input_ids"][0].tolist())
    if not tokens or tokens[0] != SRC:
        tokens = [SRC] + tokens
    result = translator.translate_batch(
        [tokens], target_prefix=[[TGT]], beam_size=4, max_decoding_length=256
    )[0]
    out_tokens = result.hypotheses[0]
    if out_tokens and out_tokens[0] == TGT:
        out_tokens = out_tokens[1:]
    return tokenizer.convert_tokens_to_string(out_tokens).strip()

def numeric_tokens(s):
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", s))

def main():
    if not Path(MODEL_DIR).exists():
        raise SystemExit(f"NLLB model directory not found: {MODEL_DIR}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, src_lang=SRC)
    translator = ctranslate2.Translator(MODEL_DIR, device="cpu", compute_type="int8")
    failures = 0
    for i, (src, expected_digits) in enumerate(CASES, 1):
        out = translate(src, tokenizer, translator)
        print(f"NLLB_CASE_{i}_SOURCE: {src}")
        print(f"NLLB_CASE_{i}_PERSIAN: {out}")
        if not out or not re.search(r"[\u0600-\u06ff]", out):
            print(f"NLLB_CASE_{i}: FAIL non-Persian/empty output")
            failures += 1
            continue
        if expected_digits and not expected_digits.issubset(numeric_tokens(out)):
            print(f"NLLB_CASE_{i}: WARN numeric preservation")
        print(f"NLLB_CASE_{i}: PASS")
    if failures:
        raise SystemExit(f"NLLB TEST FAILED: {failures} cases")
    print("NLLB TEST COMPLETE: all cases produced Persian output")

if __name__ == "__main__":
    main()
