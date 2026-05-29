
from datetime import datetime
import os
import sqlite3
from functools import wraps
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "instance" / "grace_beauty.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def load_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "grace-beauty-studio-dev-secret")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def adapt_sql(sql):
    return sql.replace("?", "%s") if USE_POSTGRES else sql


def get_db():
    if "db" not in g:
        if USE_POSTGRES:
            if psycopg is None:
                raise RuntimeError("psycopg is required when DATABASE_URL is configured.")
            g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            DATABASE.parent.mkdir(exist_ok=True)
            g.db = sqlite3.connect(DATABASE)
            g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_all(sql, params=()):
    return [dict(row) for row in get_db().execute(adapt_sql(sql), params).fetchall()]


def query_one(sql, params=()):
    row = get_db().execute(adapt_sql(sql), params).fetchone()
    return dict(row) if row else None


def execute(sql, params=()):
    db = get_db()
    db.execute(adapt_sql(sql), params)
    db.commit()


def executemany(sql, params):
    db = get_db()
    if USE_POSTGRES:
        with db.cursor() as cur:
            cur.executemany(adapt_sql(sql), params)
    else:
        db.executemany(sql, params)
    db.commit()


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file_storage, fallback=""):
    if not file_storage or not file_storage.filename or not allowed_image(file_storage.filename):
        return fallback
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    stored = f"{uuid4().hex}.{ext}"
    file_storage.save(UPLOAD_DIR / stored)
    return f"/static/uploads/{stored}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Hair styling',
    description TEXT NOT NULL DEFAULT '',
    price TEXT NOT NULL DEFAULT '',
    duration TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    is_featured INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Natural care',
    description TEXT NOT NULL DEFAULT '',
    price TEXT NOT NULL DEFAULT '',
    size TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    stock_status TEXT NOT NULL DEFAULT 'Available',
    is_featured INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    interest TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'New',
    created_at TEXT NOT NULL
);
"""
POSTGRES_SCHEMA = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")

DEFAULT_SETTINGS = {
    "studio_name": "Grace Beauty Studio",
    "tagline": "Elegant hair styling and natural care products for women who love soft, healthy beauty.",
    "hero_title": "Hair, glow, and natural care made beautifully personal.",
    "hero_subtitle": "Book protective styles, salon care, bridal looks, and shop Grace's natural ghee and shea butter products for nourished hair and skin.",
    "address": "Nairobi, Kenya",
    "phone": os.environ.get("STUDIO_PHONE", "+254 700 000 000"),
    "whatsapp": os.environ.get("STUDIO_WHATSAPP", "254700000000"),
    "instagram": "@gracebeautystudio",
    "opening_hours": "Mon - Sat, 8:00 AM - 7:00 PM",
    "booking_note": "Send a WhatsApp message to reserve a style, ask about products, or request a bridal/home service quote.",
}
DEFAULT_SERVICES = [
    ("Knotless Braids", "Protective styling", "Lightweight, neat braids finished with clean parting and hair-care guidance.", "From KSh 3,500", "4-6 hrs", "https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?auto=format&fit=crop&w=900&q=85", 1, 1, 1),
    ("Silk Press & Treatment", "Salon care", "A smooth press with deep conditioning for shine, movement, and healthier hair.", "From KSh 2,500", "2 hrs", "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=900&q=85", 1, 1, 2),
    ("Bridal & Event Styling", "Occasion styling", "Elegant updos, soft glam hair preparation, and coordinated looks for special events.", "Quote on request", "Consultation", "https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=900&q=85", 1, 1, 3),
    ("Natural Hair Care", "Salon care", "Wash, detangle, moisturize, trim, and protective finish for natural hair routines.", "From KSh 1,800", "90 mins", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 0, 1, 4),
]
DEFAULT_PRODUCTS = [
    ("Natural Hair & Skin Ghee", "Hair and skin care", "Rich natural ghee blend for sealing moisture, softening strands, and nourishing dry skin.", "KSh 850", "250g", "https://images.unsplash.com/photo-1608571423902-eed4a5ad8108?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 1),
    ("Raw Shea Butter", "Natural care", "Whipped-style shea butter for protective styling, dry elbows, hands, and natural glow routines.", "KSh 750", "200g", "https://images.unsplash.com/photo-1612817288484-6f916006741a?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 2),
    ("Hair Growth Butter", "Hair care", "A soft butter blend for scalp massage, protective styles, edges, and weekly hair-care rituals.", "KSh 950", "180g", "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 3),
]


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def init_db():
    db = get_db()
    if USE_POSTGRES:
        db.execute(POSTGRES_SCHEMA)
    else:
        db.executescript(SCHEMA)
    db.commit()
    seed_data()


def seed_data():
    for key, value in DEFAULT_SETTINGS.items():
        if not query_one("SELECT key FROM settings WHERE key = ?", (key,)):
            execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    admin_email = os.environ.get("ADMIN_EMAIL", "grace@beautystudio.local")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Grace@1234")
    if not query_one("SELECT id FROM admin_users WHERE email = ?", (admin_email,)):
        execute("INSERT INTO admin_users (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)", (admin_email, generate_password_hash(admin_password), "Grace", now_stamp()))
    if not query_one("SELECT COUNT(*) AS total FROM services")["total"]:
        executemany("INSERT INTO services (title, category, description, price, duration, image_url, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item + (now_stamp(),) for item in DEFAULT_SERVICES])
    if not query_one("SELECT COUNT(*) AS total FROM products")["total"]:
        executemany("INSERT INTO products (name, category, description, price, size, image_url, stock_status, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item + (now_stamp(),) for item in DEFAULT_PRODUCTS])


def ensure_initialized():
    if app.config.get("DB_INITIALIZED"):
        return
    init_db()
    app.config["DB_INITIALIZED"] = True


@app.before_request
def before_request():
    ensure_initialized()


def get_settings():
    return {row["key"]: row["value"] for row in query_all("SELECT key, value FROM settings")}


@app.context_processor
def inject_globals():
    return {"settings": get_settings()}


def list_services(include_inactive=False):
    clause = "" if include_inactive else "WHERE is_active = 1"
    return query_all(f"SELECT * FROM services {clause} ORDER BY is_featured DESC, sort_order ASC, id DESC")


def list_products(include_inactive=False):
    clause = "" if include_inactive else "WHERE is_active = 1"
    return query_all(f"SELECT * FROM products {clause} ORDER BY is_featured DESC, sort_order ASC, id DESC")


def admin_user():
    email = session.get("admin_email")
    return query_one("SELECT * FROM admin_users WHERE email = ?", (email,)) if email else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not admin_user():
            flash("Please sign in to manage Grace Beauty Studio.", "warning")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def checkbox_value(name):
    return 1 if request.form.get(name) == "on" else 0


@app.route("/")
def home():
    return render_template("home.html", services=list_services(), products=list_products())


@app.route("/inquire", methods=["POST"])
def inquire():
    execute("INSERT INTO inquiries (name, phone, email, interest, message, status, created_at) VALUES (?, ?, ?, ?, ?, 'New', ?)", (request.form.get("name", "").strip(), request.form.get("phone", "").strip(), request.form.get("email", "").strip(), request.form.get("interest", "").strip(), request.form.get("message", "").strip(), now_stamp()))
    flash("Thank you. Grace will follow up with you shortly.", "success")
    return redirect(url_for("home") + "#booking")


@app.route("/grace-admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query_one("SELECT * FROM admin_users WHERE email = ?", (email,))
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session["admin_email"] = user["email"]
            flash("Welcome back, Grace. Your studio shelves are ready.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin email or password. Please check the details and try again.", "error")
    return render_template("admin_login.html")


@app.route("/grace-admin/logout")
def admin_logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.route("/grace-admin")
@admin_required
def admin_dashboard():
    return render_template("admin.html", admin=admin_user(), services=list_services(True), products=list_products(True), inquiries=query_all("SELECT * FROM inquiries ORDER BY id DESC LIMIT 20"))


@app.route("/grace-admin/settings", methods=["POST"])
@admin_required
def update_settings():
    for key in ["studio_name", "tagline", "hero_title", "hero_subtitle", "address", "phone", "whatsapp", "instagram", "opening_hours", "booking_note"]:
        if USE_POSTGRES:
            execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, request.form.get(key, "").strip()))
        else:
            execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, request.form.get(key, "").strip()))
    flash("Studio content updated.", "success")
    return redirect(url_for("admin_dashboard") + "#studio")


@app.route("/grace-admin/services", methods=["POST"])
@admin_required
def save_service():
    item_id = request.form.get("id")
    image_url = save_uploaded_image(request.files.get("image_file"), request.form.get("image_url", "").strip())
    values = (request.form.get("title", "").strip(), request.form.get("category", "Hair styling").strip(), request.form.get("description", "").strip(), request.form.get("price", "").strip(), request.form.get("duration", "").strip(), image_url, checkbox_value("is_featured"), checkbox_value("is_active"), int(request.form.get("sort_order") or 0), now_stamp())
    if item_id:
        execute("UPDATE services SET title = ?, category = ?, description = ?, price = ?, duration = ?, image_url = ?, is_featured = ?, is_active = ?, sort_order = ?, updated_at = ? WHERE id = ?", values + (item_id,))
        flash("Service updated.", "success")
    else:
        execute("INSERT INTO services (title, category, description, price, duration, image_url, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        flash("Service added.", "success")
    return redirect(url_for("admin_dashboard") + "#services")


@app.route("/grace-admin/products", methods=["POST"])
@admin_required
def save_product():
    item_id = request.form.get("id")
    image_url = save_uploaded_image(request.files.get("image_file"), request.form.get("image_url", "").strip())
    values = (request.form.get("name", "").strip(), request.form.get("category", "Natural care").strip(), request.form.get("description", "").strip(), request.form.get("price", "").strip(), request.form.get("size", "").strip(), image_url, request.form.get("stock_status", "Available").strip(), checkbox_value("is_featured"), checkbox_value("is_active"), int(request.form.get("sort_order") or 0), now_stamp())
    if item_id:
        execute("UPDATE products SET name = ?, category = ?, description = ?, price = ?, size = ?, image_url = ?, stock_status = ?, is_featured = ?, is_active = ?, sort_order = ?, updated_at = ? WHERE id = ?", values + (item_id,))
        flash("Product updated.", "success")
    else:
        execute("INSERT INTO products (name, category, description, price, size, image_url, stock_status, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        flash("Product added.", "success")
    return redirect(url_for("admin_dashboard") + "#products")


@app.route("/grace-admin/services/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_service(item_id):
    execute("DELETE FROM services WHERE id = ?", (item_id,))
    flash("Service removed.", "success")
    return redirect(url_for("admin_dashboard") + "#services")


@app.route("/grace-admin/products/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_product(item_id):
    execute("DELETE FROM products WHERE id = ?", (item_id,))
    flash("Product removed.", "success")
    return redirect(url_for("admin_dashboard") + "#products")


@app.route("/grace-admin/inquiries/<int:item_id>/status", methods=["POST"])
@admin_required
def update_inquiry_status(item_id):
    execute("UPDATE inquiries SET status = ? WHERE id = ?", (request.form.get("status", "New"), item_id))
    flash("Inquiry status updated.", "success")
    return redirect(url_for("admin_dashboard") + "#inquiries")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5020)), debug=True, use_reloader=False)


