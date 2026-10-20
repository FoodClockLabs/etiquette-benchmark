"""The judging rules shared by both exams (a faithful copy of the printed-truth scorer's number test)."""
import re


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).replace(",", "."))
    return float(m.group(0)) if m else None


def agree(a, b):
    return a is not None and b is not None and abs(a - b) < max(0.05, abs(a) * 0.02)
