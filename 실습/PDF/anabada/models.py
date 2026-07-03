from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    items = db.relationship("Item", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, default=0, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default="거래가능", nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def is_free(self) -> bool:
        return self.price == 0

    def price_display(self) -> str:
        if self.is_free():
            return "무료 나눔"
        return f"{self.price:,}원"

    def image_url(self):
        from flask import url_for

        if self.image_filename:
            return url_for("static", filename=f"uploads/{self.image_filename}")
        return url_for("static", filename="img/default_item.svg")

    def is_completed(self) -> bool:
        return self.status == "거래완료"

    def status_class(self) -> str:
        mapping = {
            "거래가능": "available",
            "거래완료": "completed",
        }
        return mapping.get(self.status, "available")
