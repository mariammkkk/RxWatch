"""
NDC normalization

Problem:
  - shortages['ndc'] values look like "['0781-3220']" -> a stringified Python list, not a real list or clean string
  - NDC codes across FDA sources use inconsistent segment lengths:
      4-4   (e.g. 0781-3220)   -> labeler needs padding to 5 digits
      5-3   (e.g. 79903-084)   -> product needs padding to 4 digits
      5-4   (e.g. 80425-0025)  -> labeler-product only, no package segment
  - this function normalizes any of these into a consistent 9-digit
    labeler-product code (drops the package segment, since that's the
    level shortages data is reported at)
"""

import ast
import re
import pandas as pd


def normalize_ndc(raw) -> str | None:
    """
    convert one NDC string into a standardized 9-digit labeler-product code.
    Returns None if the input is missing or unparseable.
    """
    if pd.isna(raw):
        return None

    s = str(raw).strip()

    # handle stringified list values like "['0781-3220']" or "['a', 'b']"
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list) and len(parsed) > 0:
                s = str(parsed[0])  # take the first NDC in the list
            else:
                return None
        except (ValueError, SyntaxError):
            return None

    # strip anything that isn't a digit or dash
    s = re.sub(r"[^0-9\-]", "", s)

    parts = s.split("-")
    parts = [p for p in parts if p != ""]

    if len(parts) < 2:
        return None  # can't normalize without at least labeler + product

    labeler, product = parts[0], parts[1]

    # pad labeler to 5 digits, product to 4 digits (standard 5-4 labeler-product)
    labeler = labeler.zfill(5)
    product = product.zfill(4)

    return labeler + product  # 9-digit labeler-product code, no package segment


def expand_ndc_list(raw) -> list[str]:
    """
    for columns that may contain MULTIPLE NDCs per row (like shortages,
    where one shortage record can list several package NDCs), return a
    list of normalized NDCs instead of just the first one
    """
    if pd.isna(raw):
        return []

    s = str(raw).strip()

    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if not isinstance(parsed, list):
                parsed = [s]
        except (ValueError, SyntaxError):
            parsed = [s]
    else:
        parsed = [s]

    normalized = []
    for item in parsed:
        n = normalize_ndc(item)
        if n:
            normalized.append(n)
    return normalized


if __name__ == "__main__":
    # test the normalization functions with example inputs
    examples = [
        "['0781-3220']",
        "['72205-102', '72205-101']",
        "79903-084",
        "80425-0025",
        "0615-7951",
    ]
    for e in examples:
        print(f"{e!r:45} -> first: {normalize_ndc(e)!r:12} all: {expand_ndc_list(e)}")