#!/usr/bin/env bash
set -euo pipefail

mkdir -p app tests
cat > app/pricing.py <<'PY'
def total_with_tax(subtotal: float, tax_rate: float) -> float:
    if subtotal < 0:
        raise ValueError("subtotal must be non-negative")
    return round(subtotal + subtotal * tax_rate, 2)
PY

cat > tests/test_pricing.py <<'PY'
import pytest

from app.pricing import total_with_tax


def test_total_with_tax():
    assert total_with_tax(100.0, 0.2) == 120.0


def test_negative_subtotal_rejected():
    with pytest.raises(ValueError):
        total_with_tax(-1.0, 0.2)
PY

git init -q
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm "Add pricing helper"

cat > app/pricing.py <<'PY'
def total_with_tax(subtotal: float, tax_rate: float) -> float:
    if subtotal < 0:
        raise ValueError("subtotal must be non-negative")
    if tax_rate < 0:
        raise ValueError("tax_rate must be non-negative")
    return round(subtotal * (1 + tax_rate), 2)
PY

cat > tests/test_pricing.py <<'PY'
import pytest

from app.pricing import total_with_tax


def test_total_with_tax():
    assert total_with_tax(100.0, 0.2) == 120.0


def test_zero_tax_rate():
    assert total_with_tax(50.0, 0.0) == 50.0


def test_negative_subtotal_rejected():
    with pytest.raises(ValueError):
        total_with_tax(-1.0, 0.2)


def test_negative_tax_rate_rejected():
    with pytest.raises(ValueError):
        total_with_tax(10.0, -0.1)
PY

git diff > changes.diff
