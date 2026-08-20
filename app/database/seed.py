"""Deterministic seed data for the sales database.

Generates ~60k orders across 2024-2025 with realistic structure:
- 5 regions, 4 product categories, 12 products, 6 employees
- monthly seasonality (peak Nov-Dec) plus gradual growth
- a deliberate sales dip in August 2025 (region + product effects)
- a small number of cancelled/pending orders so status analysis works
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import text

from app.database.connection import get_engine, init_database

REGIONS = ["华东", "华南", "华北", "西南", "华中"]
CATEGORIES = ["电子产品", "家居用品", "服饰", "食品饮料"]
PRODUCTS = [
    # name, category, base price
    ("产品A", "电子产品", 1999.0),
    ("产品B", "电子产品", 2999.0),
    ("产品C", "电子产品", 999.0),
    ("产品D", "家居用品", 899.0),
    ("产品E", "家居用品", 499.0),
    ("产品F", "家居用品", 299.0),
    ("产品G", "服饰", 399.0),
    ("产品H", "服饰", 199.0),
    ("产品I", "服饰", 599.0),
    ("产品J", "食品饮料", 99.0),
    ("产品K", "食品饮料", 59.0),
    ("产品L", "食品饮料", 39.0),
]
REGION_WEIGHTS = {"华东": 0.34, "华南": 0.24, "华北": 0.20, "西南": 0.12, "华中": 0.10}
GENDERS = ["男", "女"]


def _monthly_factor(year: int, month: int) -> float:
    """Seasonality: Q4 peak, Jan/Feb low. 2025 overall ~+18% vs 2024."""
    base = {
        1: 0.72, 2: 0.68, 3: 0.85, 4: 0.90, 5: 0.95, 6: 1.00,
        7: 0.98, 8: 0.92, 9: 1.02, 10: 1.12, 11: 1.28, 12: 1.35,
    }[month]
    growth = 1.18 if year == 2025 else 1.0
    return base * growth


def _august_2025_dip(region: str, product_name: str, month: int, year: int) -> float:
    """August 2025: 华东 -23%, product A -18% (drives the demo finding)."""
    if (year, month) != (2025, 8):
        return 1.0
    factor = 1.0
    if region == "华东":
        factor *= 0.77
    if product_name == "产品A":
        factor *= 0.82
    return factor


def _customer_name(i: int, used: set[str], rng: random.Random) -> str:
    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    while True:
        name = rng.choice(surnames) + rng.choice("伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英")
        if name not in used:
            used.add(name)
            return name


def seed_database(regenerate: bool = False) -> None:
    """Create and populate the database.

    Args:
        regenerate: Drop the existing DB file and rebuild from scratch.
    """
    if regenerate:
        init_database(drop_existing=True)
    else:
        init_database()

    engine = get_engine()
    rng = random.Random(42)

    with engine.begin() as conn:
        # customers
        used_names: set[str] = set()
        customers = [
            (i, _customer_name(i, used_names, rng), rng.choices(list(REGION_WEIGHTS), weights=list(REGION_WEIGHTS.values()))[0],
             rng.choice(GENDERS), rng.randint(18, 70))
            for i in range(1, 2001)
        ]
        conn.execute(text("DELETE FROM customers"))
        conn.executemany(
            "INSERT INTO customers (id, name, region, gender, age) VALUES (:id, :name, :region, :gender, :age)",
            [dict(id=c[0], name=c[1], region=c[2], gender=c[3], age=c[4]) for c in customers],
        )

        # regions
        conn.execute(text("DELETE FROM regions"))
        conn.executemany(
            "INSERT INTO regions (id, name) VALUES (:id, :name)",
            [dict(id=i + 1, name=r) for i, r in enumerate(REGIONS)],
        )

        # employees
        conn.execute(text("DELETE FROM employees"))
        employees = [
            (1, "张伟", "华东", "销售部"),
            (2, "李娜", "华南", "销售部"),
            (3, "王强", "华北", "销售部"),
            (4, "刘敏", "西南", "销售部"),
            (5, "陈静", "华中", "销售部"),
            (6, "杨磊", "华东", "市场部"),
        ]
        conn.executemany(
            "INSERT INTO employees (id, name, region, department) VALUES (:id, :name, :region, :department)",
            [dict(id=e[0], name=e[1], region=e[2], department=e[3]) for e in employees],
        )

        # products
        conn.execute(text("DELETE FROM products"))
        conn.executemany(
            "INSERT INTO products (id, name, category, price) VALUES (:id, :name, :category, :price)",
            [dict(id=i + 1, name=p[0], category=p[1], price=p[2]) for i, p in enumerate(PRODUCTS)],
        )

        # orders + order_items
        conn.execute(text("DELETE FROM order_items"))
        conn.execute(text("DELETE FROM orders"))

        statuses = ["completed", "completed", "completed", "completed", "cancelled", "pending"]
        order_rows = []
        item_rows = []
        order_id = 1
        item_id = 1

        day = date(2024, 1, 1)
        end = date(2025, 12, 31)
        while day <= end:
            factor = _monthly_factor(day.year, day.month)
            n_daily = int(rng.gauss(95, 18) * factor)
            n_daily = max(20, min(320, n_daily))
            for _ in range(n_daily):
                customer_id = rng.randint(1, 2000)
                region = customers[customer_id - 1][2]
                status = rng.choice(statuses)
                amount = 0.0
                n_items = rng.choices([1, 2, 3, 4, 5], weights=[50, 28, 14, 6, 2])[0]
                chosen = rng.sample(range(1, 13), n_items)
                items = []
                for pid in chosen:
                    pname, _cat, price = PRODUCTS[pid - 1]
                    qty = rng.randint(1, 6)
                    line_total = price * qty * _august_2025_dip(region, pname, day.month, day.year)
                    # small random discount
                    line_total *= rng.uniform(0.92, 1.0)
                    amount += line_total
                    items.append((item_id, order_id, pid, qty, round(price, 2)))
                    item_id += 1
                amount = round(amount, 2)
                if status != "cancelled":
                    order_rows.append((order_id, customer_id, day.isoformat(), amount, status))
                    for it in items:
                        item_rows.append(it)
                order_id += 1
            day += timedelta(days=1)

        conn.executemany(
            "INSERT INTO orders (id, customer_id, order_date, amount, status) VALUES (:id, :customer_id, :order_date, :amount, :status)",
            [dict(id=r[0], customer_id=r[1], order_date=r[2], amount=r[3], status=r[4]) for r in order_rows],
        )
        conn.executemany(
            "INSERT INTO order_items (id, order_id, product_id, quantity, price) VALUES (:id, :order_id, :product_id, :quantity, :price)",
            [dict(id=r[0], order_id=r[1], product_id=r[2], quantity=r[3], price=r[4]) for r in item_rows],
        )

    print(
        f"Seeded database: {len(order_rows):,} orders, {len(item_rows):,} order_items, "
        f"{len(customers):,} customers, {len(PRODUCTS)} products."
    )


if __name__ == "__main__":
    seed_database(regenerate=True)
