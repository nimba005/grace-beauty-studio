
from datetime import datetime
import json
import os
import sqlite3
from functools import wraps
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
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
CREATE TABLE IF NOT EXISTS testimonials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    tag TEXT NOT NULL DEFAULT '',
    is_approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL DEFAULT '',
    item_id INTEGER NOT NULL DEFAULT 0,
    item_name TEXT NOT NULL DEFAULT '',
    rating INTEGER NOT NULL DEFAULT 5,
    message TEXT NOT NULL DEFAULT '',
    is_approved INTEGER NOT NULL DEFAULT 0,
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
    "email": os.environ.get("STUDIO_EMAIL", "ptrulina50@gmail.com"),
    "phone": os.environ.get("STUDIO_PHONE", "+254700549855"),
    "whatsapp": os.environ.get("STUDIO_WHATSAPP", "25439735584"),
    "linkedin": os.environ.get("STUDIO_LINKEDIN", "https://www.linkedin.com/"),
    "instagram": "@gracebeautystudio",
    "opening_hours": "Mon - Sat, 8:00 AM - 7:00 PM",
    "booking_note": "Send a WhatsApp message to reserve a style, ask about products, or request a bridal/home service quote.",
}
DEFAULT_SERVICES = [
    ("Knotless Braids", "Braids", "Lightweight, neat knotless braids with clean parting, soft tension control, and care guidance for longer wear.", "From KSh 3,500", "4-6 hrs", "https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?auto=format&fit=crop&w=900&q=85", 1, 1, 1),
    ("Soft Locs", "Locs", "A protective loc style with a soft natural finish, ideal for elegant everyday wear and low-maintenance styling.", "From KSh 4,500", "4-6 hrs", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 1, 1, 2),
    ("Children Cornrows", "Children styles", "Gentle cornrows for girls with age-friendly tension, neat lines, and optional beads or simple creative patterns.", "From KSh 1,200", "1-2 hrs", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 1, 1, 3),
    ("Bridal & Event Styling", "Bridal and events", "Elegant updos, soft glam hair preparation, and coordinated looks for weddings, shoots, and special occasions.", "Quote on request", "Consultation", "https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=900&q=85", 1, 1, 4),
    ("Natural Hair Care", "Natural hair care", "Wash, detangle, moisturize, trim, and protective finish for natural hair routines and healthy growth plans.", "From KSh 1,800", "90 mins", "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=900&q=85", 0, 1, 5),
]
AFRICAN_SERVICE_CATALOG = [
    ("Box Braids", "Braids", "Classic long-lasting braids with clean sectioning, sealed ends, and styling options for school, work, or events.", "From KSh 3,000", "4-6 hrs", "https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=900&q=85", 0, 1, 6),
    ("Fulani Braids", "Braids", "A stylish braided look with front detail, optional beads, and a polished finish inspired by African braid artistry.", "From KSh 3,800", "4-5 hrs", "https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=900&q=85", 0, 1, 7),
    ("Goddess Braids", "Braids", "Statement braids with soft curls added for a feminine finish that works beautifully for holidays and events.", "From KSh 4,200", "4-6 hrs", "https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?auto=format&fit=crop&w=900&q=85", 0, 1, 8),
    ("Butterfly Locs", "Locs", "Textured locs with a light distressed finish for a modern protective style with volume and personality.", "From KSh 4,800", "5-7 hrs", "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=900&q=85", 0, 1, 9),
    ("Starter Locs", "Locs", "Clean starter loc installation with parting guidance, scalp care, and a simple maintenance plan.", "From KSh 2,500", "2-3 hrs", "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=900&q=85", 0, 1, 10),
    ("Loc Retwist", "Locs", "Gentle retwist, scalp refresh, and neat finishing for mature locs without over-tensioning the roots.", "From KSh 1,800", "90 mins", "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=900&q=85", 0, 1, 11),
    ("Flat Twists", "Natural hair care", "Low-tension flat twists for natural hair, ideal for protective styling, growth breaks, and soft everyday looks.", "From KSh 1,500", "1-2 hrs", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 0, 1, 12),
    ("Twist Out Prep", "Natural hair care", "Hydrating wash, stretch, and twist preparation for defined curls and easier weekly natural hair maintenance.", "From KSh 1,800", "2 hrs", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 0, 1, 13),
    ("Deep Treatment & Steam", "Treatments", "Moisture-focused treatment and steam care for dry, brittle, or recently unbraided hair.", "From KSh 1,500", "75 mins", "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=900&q=85", 0, 1, 14),
    ("Silk Press & Trim", "Treatments", "Smooth press, deep conditioning, and light trim for clients who want movement, shine, and shape.", "From KSh 2,800", "2 hrs", "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=900&q=85", 0, 1, 15),
    ("Girls Beaded Braids", "Children styles", "Cute child-friendly braids with beads, soft edges, and careful tension control for young girls.", "From KSh 1,500", "2-3 hrs", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 0, 1, 16),
    ("School Lines", "Children styles", "Simple, neat school-ready cornrows that are quick, clean, and easy to maintain during the week.", "From KSh 800", "45-90 mins", "https://images.unsplash.com/photo-1605980776566-0486c3ac7617?auto=format&fit=crop&w=900&q=85", 0, 1, 17),
    ("Traditional Bridal Braids", "Bridal and events", "Refined bridal braids with clean detail, accessories, and consultation for outfit and ceremony coordination.", "Quote on request", "Consultation", "https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=900&q=85", 0, 1, 18),
]
DEFAULT_PRODUCTS = [
    ("Natural Hair & Skin Ghee", "Hair and skin care", "Rich natural ghee blend for sealing moisture, softening strands, and nourishing dry skin.", "KSh 850", "250g", "https://images.unsplash.com/photo-1608571423902-eed4a5ad8108?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 1),
    ("Raw Shea Butter", "Natural care", "Whipped-style shea butter for protective styling, dry elbows, hands, and natural glow routines.", "KSh 750", "200g", "https://images.unsplash.com/photo-1612817288484-6f916006741a?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 2),
    ("Hair Growth Butter", "Hair care", "A soft butter blend for scalp massage, protective styles, edges, and weekly hair-care rituals.", "KSh 950", "180g", "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=900&q=85", "Available", 1, 1, 3),
]
DEFAULT_TESTIMONIALS = [
    ("Achieng", "Soft finish, clean service", "Grace understood exactly what I wanted and the final look stayed neat and comfortable.", "Protective styling", 1),
    ("Mercy", "The shea butter is now a routine", "The product feels rich without being heavy, and my skin stays moisturized for longer.", "Natural care", 1),
    ("Njeri", "Professional and warm", "Booking was simple, the advice was honest, and the service felt very personal.", "Salon experience", 1),
]
SERVICE_IMAGE_PATHS = {
    "Knotless Braids": "/static/images/knotless%20braids.jpeg",
    "Box Braids": "/static/images/box%20braids.jpeg",
    "Fulani Braids": "/static/images/fulani%20braids.jpeg",
    "Goddess Braids": "/static/images/Godes%20Braids.jpeg",
    "Bridal & Event Styling": "/static/images/Bridal%20%26%20Event%20Styling.jpg",
    "Traditional Bridal Braids": "/static/images/Traditional%20Bridal%20Braids.jpeg",
    "Girls Beaded Braids": "/static/images/Girls%20Beaded%20Braids.jpeg",
    "School Lines": "/static/images/School%20Lines.jpeg",
    "Butterfly Locs": "/static/images/butterfly%20locks.jpg",
    "Starter Locs": "/static/images/starter%20locks.jpeg",
    "Loc Retwist": "/static/images/lock%20retwists.jpeg",
    "Natural Hair Care": "/static/images/Natural%20Hair%20Care.jpegp",
    "Flat Twists": "/static/images/Flat%20Twists.jpeg",
    "Twist Out Prep": "/static/images/Twist%20Out%20Prep.jpg",
    "Silk Press & Treatment": "/static/images/Silk%20Press%20%26%20Treatment.jpeg",
    "Deep Treatment & Steam": "/static/images/Deep%20Treatment%20%26%20Steam.jpeg",
    "Silk Press & Trim": "/static/images/Silk%20Press%20%26%20Trim.jpeg",
}


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
    for key in ["email", "phone", "whatsapp"]:
        if USE_POSTGRES:
            execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, DEFAULT_SETTINGS[key]))
        else:
            execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, DEFAULT_SETTINGS[key]))
    admin_email = os.environ.get("ADMIN_EMAIL", "ptrulina50@gmail.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Grace@1234")
    if not query_one("SELECT id FROM admin_users WHERE email = ?", (admin_email,)):
        execute("INSERT INTO admin_users (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)", (admin_email, generate_password_hash(admin_password), "Grace", now_stamp()))
    if not query_one("SELECT COUNT(*) AS total FROM services")["total"]:
        executemany("INSERT INTO services (title, category, description, price, duration, image_url, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item + (now_stamp(),) for item in DEFAULT_SERVICES])
    for item in DEFAULT_SERVICES:
        if query_one("SELECT id FROM services WHERE title = ?", (item[0],)):
            execute("UPDATE services SET category = ?, description = ?, price = ?, duration = ?, image_url = ?, sort_order = ?, updated_at = ? WHERE title = ?", (item[1], item[2], item[3], item[4], item[5], item[8], now_stamp(), item[0]))
    for item in AFRICAN_SERVICE_CATALOG:
        if not query_one("SELECT id FROM services WHERE title = ?", (item[0],)):
            execute("INSERT INTO services (title, category, description, price, duration, image_url, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", item + (now_stamp(),))
    for title, image_url in SERVICE_IMAGE_PATHS.items():
        execute("UPDATE services SET image_url = ?, updated_at = ? WHERE title = ?", (image_url, now_stamp(), title))
    if not query_one("SELECT COUNT(*) AS total FROM products")["total"]:
        executemany("INSERT INTO products (name, category, description, price, size, image_url, stock_status, is_featured, is_active, sort_order, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item + (now_stamp(),) for item in DEFAULT_PRODUCTS])
    if not query_one("SELECT COUNT(*) AS total FROM testimonials")["total"]:
        executemany("INSERT INTO testimonials (customer_name, title, message, tag, is_approved, created_at) VALUES (?, ?, ?, ?, ?, ?)", [item + (now_stamp(),) for item in DEFAULT_TESTIMONIALS])


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


def group_services(services):
    order = ["Braids", "Locs", "Children styles", "Natural hair care", "Treatments", "Bridal and events"]
    grouped = []
    for category in order:
        items = [service for service in services if service["category"] == category]
        if items:
            grouped.append({"name": category, "services": items})
    for category in sorted({service["category"] for service in services} - set(order)):
        grouped.append({"name": category, "services": [service for service in services if service["category"] == category]})
    return grouped


def list_products(include_inactive=False):
    clause = "" if include_inactive else "WHERE is_active = 1"
    return query_all(f"SELECT * FROM products {clause} ORDER BY is_featured DESC, sort_order ASC, id DESC")


def list_testimonials(include_pending=False):
    clause = "" if include_pending else "WHERE is_approved = 1"
    return query_all(f"SELECT * FROM testimonials {clause} ORDER BY is_approved DESC, id DESC")


def list_reviews(include_pending=False):
    clause = "" if include_pending else "WHERE is_approved = 1"
    return query_all(f"SELECT * FROM reviews {clause} ORDER BY is_approved DESC, id DESC")


def customer_has_interacted(phone, email):
    phone = (phone or "").strip()
    email = (email or "").strip().lower()
    if phone:
        if query_one("SELECT id FROM inquiries WHERE phone = ? LIMIT 1", (phone,)):
            return True
    if email:
        if query_one("SELECT id FROM inquiries WHERE lower(email) = ? LIMIT 1", (email,)):
            return True
    return False


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
    services = list_services()
    products = list_products()
    return render_template(
        "home.html",
        services=services,
        service_groups=group_services(services),
        products=products,
        testimonials=list_testimonials(),
        reviews=list_reviews(),
        review_items={"services": services, "products": products},
    )


@app.route("/inquire", methods=["POST"])
def inquire():
    payload = request.get_json(silent=True) or request.form
    name = (payload.get("name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    interest = (payload.get("interest") or "").strip()
    message = (payload.get("message") or "").strip()
    cart_summary = (payload.get("cart_summary") or "").strip()
    if cart_summary:
        message = f"{message}\n\nSelected items:\n{cart_summary}".strip()
    if not name or not phone:
        if request.is_json:
            return jsonify({"ok": False, "error": "Please add your name and phone or WhatsApp number."}), 400
        flash("Please add your name and phone or WhatsApp number.", "error")
        return redirect(url_for("home") + "#booking")
    execute("INSERT INTO inquiries (name, phone, email, interest, message, status, created_at) VALUES (?, ?, ?, ?, ?, 'New', ?)", (name, phone, email, interest, message, now_stamp()))
    if request.is_json:
        return jsonify({"ok": True, "message": "Thank you. Grace will follow up with you shortly."})
    flash("Thank you. Grace will follow up with you shortly.", "success")
    return redirect(url_for("home") + "#booking")


@app.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    cart = payload.get("cart") or []
    if not message:
        return jsonify({"ok": False, "reply": "Please type what you need help with."}), 400
    services = list_services()
    products = list_products()
    catalog = {
        "services": [{"id": item["id"], "title": item["title"], "category": item["category"], "price": item["price"], "duration": item["duration"]} for item in services],
        "products": [{"id": item["id"], "name": item["name"], "category": item["category"], "price": item["price"], "size": item["size"]} for item in products],
    }
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return jsonify({"ok": True, "reply": "I can help you choose a style or product. Tell me if you want braids, locs, children styles, natural care, treatments, bridal styling, or products, then add your choice to the cart and submit a booking."})
    prompt = (
        "You are Grace Beauty Studio's concise shopping and service guide in Nairobi. "
        "Help customers understand the provided products and services, compare options, and suggest what to add to cart. "
        "Do not provide direct contact details, do not invent prices, and keep replies under 90 words."
    )
    data = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"message": message, "cart": cart, "catalog": catalog})},
        ],
    }
    try:
        req = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(data).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        reply = result.get("output_text", "").strip()
        if not reply:
            parts = result.get("output", [])
            reply = " ".join(
                content.get("text", "")
                for item in parts
                for content in item.get("content", [])
                if content.get("type") in {"output_text", "text"}
            ).strip()
        return jsonify({"ok": True, "reply": reply or "I can help you choose and book. What style or product are you interested in?"})
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return jsonify({"ok": True, "reply": "I can help with booking, but the AI service is not reachable right now. Add the product or service to cart, then submit your booking details and Grace will follow up."})


@app.route("/testimonials", methods=["POST"])
def submit_testimonial():
    name = request.form.get("customer_name", "").strip()
    message = request.form.get("message", "").strip()
    if not name or not message:
        flash("Please add your name and testimony before submitting.", "error")
        return redirect(url_for("home") + "#testimonials")
    execute(
        "INSERT INTO testimonials (customer_name, title, message, tag, is_approved, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (name, request.form.get("title", "").strip(), message, request.form.get("tag", "").strip(), now_stamp()),
    )
    flash("Thank you. Your testimony has been received and will appear after review.", "success")
    return redirect(url_for("home") + "#testimonials")


@app.route("/reviews", methods=["POST"])
def submit_review():
    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    item_type = request.form.get("item_type", "").strip()
    item_id = int(request.form.get("item_id") or 0)
    message = request.form.get("message", "").strip()
    rating = max(1, min(5, int(request.form.get("rating") or 5)))
    if not name or not message or item_type not in {"service", "product"} or not item_id:
        flash("Please complete the review form before submitting.", "error")
        return redirect(url_for("home") + "#reviews")
    if not customer_has_interacted(phone, email):
        flash("Please use the phone or email from a previous booking or order request so we can verify your review.", "warning")
        return redirect(url_for("home") + "#reviews")
    table = "services" if item_type == "service" else "products"
    name_column = "title" if item_type == "service" else "name"
    item = query_one(f"SELECT {name_column} AS item_name FROM {table} WHERE id = ?", (item_id,))
    if not item:
        flash("We could not find the selected service or product.", "error")
        return redirect(url_for("home") + "#reviews")
    execute(
        "INSERT INTO reviews (customer_name, phone, email, item_type, item_id, item_name, rating, message, is_approved, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
        (name, phone, email, item_type, item_id, item["item_name"], rating, message, now_stamp()),
    )
    flash("Thank you. Your review has been submitted and will appear after approval.", "success")
    return redirect(url_for("home") + "#reviews")


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
    return render_template(
        "admin.html",
        admin=admin_user(),
        services=list_services(True),
        products=list_products(True),
        inquiries=query_all("SELECT * FROM inquiries ORDER BY id DESC LIMIT 20"),
        testimonials=list_testimonials(True),
        reviews=list_reviews(True),
    )


@app.route("/grace-admin/settings", methods=["POST"])
@admin_required
def update_settings():
    for key in ["studio_name", "tagline", "hero_title", "hero_subtitle", "address", "email", "phone", "whatsapp", "linkedin", "instagram", "opening_hours", "booking_note"]:
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


@app.route("/grace-admin/testimonials/<int:item_id>/status", methods=["POST"])
@admin_required
def update_testimonial_status(item_id):
    execute("UPDATE testimonials SET is_approved = ? WHERE id = ?", (checkbox_value("is_approved"), item_id))
    flash("Testimony visibility updated.", "success")
    return redirect(url_for("admin_dashboard") + "#testimonials")


@app.route("/grace-admin/testimonials/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_testimonial(item_id):
    execute("DELETE FROM testimonials WHERE id = ?", (item_id,))
    flash("Testimony removed.", "success")
    return redirect(url_for("admin_dashboard") + "#testimonials")


@app.route("/grace-admin/reviews/<int:item_id>/status", methods=["POST"])
@admin_required
def update_review_status(item_id):
    execute("UPDATE reviews SET is_approved = ? WHERE id = ?", (checkbox_value("is_approved"), item_id))
    flash("Review visibility updated.", "success")
    return redirect(url_for("admin_dashboard") + "#reviews")


@app.route("/grace-admin/reviews/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_review(item_id):
    execute("DELETE FROM reviews WHERE id = ?", (item_id,))
    flash("Review removed.", "success")
    return redirect(url_for("admin_dashboard") + "#reviews")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5020)), debug=True, use_reloader=False)


