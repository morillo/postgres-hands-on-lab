"""Lab 3.5: SQLAlchemy 2.0 ORM. Map the existing tables to Python classes, query, and write."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from settings import sa_url


class Base(DeclarativeBase):
    """Common parent class of every mapped class."""


class Customer(Base):
    """One row of the customers table."""

    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str]
    name: Mapped[str]
    country: Mapped[str]
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", order_by="Order.id")


class Product(Base):
    """One row of the products table."""

    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str]
    name: Mapped[str]
    price: Mapped[Decimal]
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Order(Base):
    """One row of the orders table."""

    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str]
    ordered_at: Mapped[datetime]
    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")


class OrderItem(Base):
    """One row of the order_items table: one product in one order."""

    __tablename__ = "order_items"
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    qty: Mapped[int]
    unit_price: Mapped[Decimal]
    product: Mapped[Product] = relationship()


def main() -> None:
    """Query through the ORM, follow relationships, then insert and remove one order."""
    engine = create_engine(sa_url())

    # 1. A query built in Python: revenue per country for shipped orders.
    revenue_by_country = (
        select(Customer.country, func.sum(OrderItem.qty * OrderItem.unit_price).label("revenue"))
        .join(Customer.orders)
        .join(Order.items)
        .where(Order.status == "shipped")
        .group_by(Customer.country)
        .order_by(Customer.country)
    )
    print("SQL that will be sent:")
    print(revenue_by_country.compile(engine))
    print()

    with Session(engine) as session:
        for row in session.execute(revenue_by_country):
            print(row.country, row.revenue)

        # 2. Follow relationships from one object to related objects.
        customer = session.get_one(Customer, 42)
        first_order = customer.orders[0]
        first_item = first_order.items[0]
        print()
        print(customer.name, "has", len(customer.orders), "orders")
        print(
            "first order has",
            len(first_order.items),
            "item(s); first product:",
            first_item.product.sku,
        )

    # 3. Remove leftovers from an earlier interrupted run, so the script can be re-run.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        leftover = session.scalar(select(Customer).where(Customer.email == "orm@example.com"))
        if leftover is not None:
            for order in leftover.orders:
                session.delete(order)
            session.delete(leftover)

    # 4. Write: one customer, one order, two order lines, in one transaction.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        new_customer = Customer(email="orm@example.com", name="Orm User", country="DE")
        keyboard = session.get_one(Product, 1)
        headphones = session.get_one(Product, 2)
        new_order = Order(
            customer=new_customer, status="new", ordered_at=datetime.now().astimezone()
        )
        new_order.items = [
            OrderItem(product=keyboard, qty=2, unit_price=keyboard.price),
            OrderItem(product=headphones, qty=1, unit_price=headphones.price),
        ]
        session.add(new_order)
        session.flush()
        new_customer_id = new_customer.id
        new_order_id = new_order.id
    print()
    print("inserted customer", new_customer_id, "and order", new_order_id)

    # 5. Clean up so the lab stays repeatable.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        session.delete(session.get_one(Order, new_order_id))
        session.delete(session.get_one(Customer, new_customer_id))
    print("cleaned up")


if __name__ == "__main__":
    main()
