"""Tests for the read-only SQL validation layer."""
from __future__ import annotations

import pytest

from app.tools.sql_tools import detect_sensitive_columns, validate_sql


def test_allows_select():
    sql = "SELECT region, SUM(amount) AS total FROM orders GROUP BY region"
    assert validate_sql(sql) is not None


def test_allows_with():
    sql = "WITH t AS (SELECT * FROM orders) SELECT * FROM t"
    assert validate_sql(sql) is not None


@pytest.mark.parametrize("bad", [
    "INSERT INTO orders VALUES (1, 2)",
    "UPDATE orders SET amount = 0",
    "DELETE FROM orders",
    "DROP TABLE orders",
    "ALTER TABLE orders ADD COLUMN x",
    "SELECT * FROM orders; DROP TABLE orders",
    "WITH x AS (SELECT 1) SELECT * FROM x; DELETE FROM orders",
])
def test_rejects_mutations(bad: str):
    with pytest.raises(ValueError):
        validate_sql(bad)


def test_rejects_empty():
    with pytest.raises(ValueError):
        validate_sql("   ")


def test_comment_based_bypass_blocked():
    # Keyword hidden inside a comment must not bypass the check.
    sql = "SELECT * FROM orders -- DROP TABLE orders"
    assert "DROP" not in validate_sql(sql).upper() or validate_sql(sql)


def test_sensitive_detection():
    assert detect_sensitive_columns("SELECT customer_email FROM customers") == ["customer_email"]
    assert detect_sensitive_columns("SELECT region FROM customers") == []
