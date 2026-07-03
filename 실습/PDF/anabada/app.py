"""
아나바다 - 물품 공유 및 중고 거래 웹 애플리케이션
"""

import os
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from models import Item, User, db

# ---------------------------------------------------------------------------
# Flask 앱 설정
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///anabada.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
STATUSES = ["거래가능", "거래완료"]

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "로그인이 필요합니다."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file) -> str | None:
    if file and file.filename and allowed_file(file.filename):
        ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return filename
    return None


def delete_image_file(filename: str):
    if filename:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.exists(filepath):
            os.remove(filepath)


def parse_item_form(form) -> dict:
    is_free = form.get("is_free") == "on"
    price = 0 if is_free else int(form.get("price", 0) or 0)
    if price == 0:
        is_free = True

    return {
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "price": price,
        "is_free": is_free,
        "status": form.get("status", "거래가능"),
    }


def author_required(f):
    @wraps(f)
    def decorated(item_id, *args, **kwargs):
        item = db.session.get(Item, item_id)
        if not item:
            flash("해당 물품을 찾을 수 없습니다.", "danger")
            return redirect(url_for("index"))
        if item.author_id != current_user.id:
            flash("본인이 등록한 물품만 수정할 수 있습니다.", "danger")
            return redirect(url_for("item_detail", item_id=item_id))
        return f(item, *args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# 인증 라우트
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not username or not password:
            flash("사용자 이름과 비밀번호를 입력해 주세요.", "danger")
            return render_template("register.html")

        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.", "danger")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("이미 사용 중인 사용자 이름입니다.", "danger")
            return render_template("register.html")

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("회원가입이 완료되었습니다. 로그인해 주세요.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            flash(f"{user.username}님, 환영합니다!", "success")
            return redirect(next_page or url_for("index"))

        flash("사용자 이름 또는 비밀번호가 올바르지 않습니다.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# 물품 라우트
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    search_query = request.args.get("q", "").strip()
    free_only = request.args.get("free_only") == "on"

    query = Item.query

    if search_query:
        query = query.filter(
            db.or_(
                Item.title.contains(search_query),
                Item.description.contains(search_query),
            )
        )

    if free_only:
        query = query.filter(Item.price == 0)

    items = query.order_by(Item.created_at.desc()).all()

    return render_template(
        "index.html",
        items=items,
        search_query=search_query,
        free_only=free_only,
    )


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def item_new():
    if request.method == "POST":
        data = parse_item_form(request.form)

        if not data["title"] or not data["description"]:
            flash("물품명과 설명은 필수 입력 항목입니다.", "danger")
            return render_template(
                "item_form.html",
                item=None,
                statuses=STATUSES,
                form_data=data,
            )

        image_filename = save_uploaded_image(request.files.get("image"))

        item = Item(
            title=data["title"],
            description=data["description"],
            image_filename=image_filename,
            price=data["price"],
            status="거래가능",
            author_id=current_user.id,
        )
        db.session.add(item)
        db.session.commit()

        flash("물품이 성공적으로 등록되었습니다!", "success")
        return redirect(url_for("item_detail", item_id=item.id))

    return render_template(
        "item_form.html",
        item=None,
        statuses=STATUSES,
        form_data=None,
    )


@app.route("/items/<int:item_id>")
def item_detail(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        flash("해당 물품을 찾을 수 없습니다.", "danger")
        return redirect(url_for("index"))
    return render_template("item_detail.html", item=item)


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
@author_required
def item_edit(item):
    if request.method == "POST":
        data = parse_item_form(request.form)

        if not data["title"] or not data["description"]:
            flash("물품명과 설명은 필수 입력 항목입니다.", "danger")
            return render_template(
                "item_form.html",
                item=item,
                statuses=STATUSES,
                form_data=data,
            )

        new_image = save_uploaded_image(request.files.get("image"))
        if new_image:
            delete_image_file(item.image_filename)
            item.image_filename = new_image

        item.title = data["title"]
        item.description = data["description"]
        item.price = data["price"]
        item.status = data["status"]
        item.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        flash("물품 정보가 수정되었습니다.", "success")
        return redirect(url_for("item_detail", item_id=item.id))

    return render_template(
        "item_form.html",
        item=item,
        statuses=STATUSES,
        form_data=None,
    )


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
@author_required
def item_delete(item):
    delete_image_file(item.image_filename)
    db.session.delete(item)
    db.session.commit()

    flash("물품이 삭제되었습니다.", "success")
    return redirect(url_for("index"))


@app.route("/items/<int:item_id>/toggle_status", methods=["POST"])
@login_required
@author_required
def toggle_status(item):
    if item.status == "거래가능":
        item.status = "거래완료"
        message = "거래가 완료되었습니다."
    else:
        item.status = "거래가능"
        message = "거래 가능 상태로 변경되었습니다."

    item.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(message, "success")
    return redirect(url_for("item_detail", item_id=item.id))


# ---------------------------------------------------------------------------
# 앱 초기화
# ---------------------------------------------------------------------------
def init_db():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.create_all()


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
