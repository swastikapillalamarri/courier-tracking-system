"""
Courier Tracking Management System
----------------------------------
A small web app built with Flask (web framework) and SQLite (built-in database).

How to run:
    1. pip install flask
    2. python app.py
    3. Open http://127.0.0.1:5000 in your browser

Admin login:  username = admin   password = admin123
User login:   username = ravi    password = user123   (or sign up a new user)
"""

import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# Basic setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "courier-tracking-secret-key"   # needed for login sessions

DATABASE = Path(__file__).parent / "courier.db"  # database file sits next to app.py

# A parcel moves through these stages, always in this order.
STATUSES = ["Booked", "Picked Up", "In Transit", "Out for Delivery", "Delivered"]

PARCEL_TYPES = ["Document", "Parcel", "Electronics", "Clothing", "Fragile", "Other"]

DATE_FORMAT = "%Y-%m-%d %H:%M"   # how dates are saved in the database


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open one database connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row          # lets us use row["column_name"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    """Close the connection when the request is finished."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def create_tables():
    """Create the three tables if they do not exist yet."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT NOT NULL DEFAULT '',
            phone         TEXT NOT NULL DEFAULT '',
            role          TEXT NOT NULL DEFAULT 'user'   -- 'admin' or 'user'
        );

        CREATE TABLE IF NOT EXISTS couriers (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id       TEXT UNIQUE NOT NULL,
            sender_name       TEXT NOT NULL,
            sender_phone      TEXT NOT NULL,
            origin            TEXT NOT NULL,
            receiver_name     TEXT NOT NULL,
            receiver_phone    TEXT NOT NULL,
            receiver_address  TEXT NOT NULL,
            destination       TEXT NOT NULL,
            parcel_type       TEXT NOT NULL,
            weight            REAL NOT NULL,
            status            TEXT NOT NULL,
            booked_on         TEXT NOT NULL,
            expected_delivery TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tracking_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            courier_id INTEGER NOT NULL,
            status     TEXT NOT NULL,
            location   TEXT NOT NULL,
            remarks    TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (courier_id) REFERENCES couriers (id) ON DELETE CASCADE
        );
    """)

    # If courier.db was made by the first version of this project, the users
    # table is missing the new columns. Add them so the old data keeps working.
    columns = [row["name"] for row in db.execute("PRAGMA table_info(users)")]
    if "role" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        db.execute("UPDATE users SET role = 'admin', full_name = 'Administrator' "
                   "WHERE username = 'admin'")
    db.commit()


def generate_tracking_id():
    """Make a unique tracking ID such as CT48201735."""
    db = get_db()
    while True:
        tracking_id = "CT" + str(random.randint(10000000, 99999999))
        exists = db.execute(
            "SELECT 1 FROM couriers WHERE tracking_id = ?", (tracking_id,)
        ).fetchone()
        if not exists:
            return tracking_id


def add_sample_data():
    """Fill a brand-new database with an admin user and a few couriers."""
    db = get_db()

    if db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 0:
        db.execute(
            """INSERT INTO users (username, password_hash, full_name, phone, role)
               VALUES (?, ?, ?, ?, ?)""",
            ("admin", generate_password_hash("admin123"), "Administrator", "", "admin"),
        )

    # A demo customer. His phone matches the sender of sample courier CT10000001.
    if db.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0] == 0:
        db.execute(
            """INSERT INTO users (username, password_hash, full_name, phone, role)
               VALUES (?, ?, ?, ?, ?)""",
            ("ravi", generate_password_hash("user123"), "Ravi Kumar", "9848012345", "user"),
        )

    if db.execute("SELECT COUNT(*) FROM couriers").fetchone()[0] == 0:
        # (tracking id, sender, sender phone, origin, receiver, receiver phone,
        #  address, destination, type, weight, number of stages completed, days ago)
        samples = [
            ("CT10000001", "Ravi Kumar", "9848012345", "Hyderabad",
             "Anita Sharma", "9811122233", "14 MG Road, Indiranagar", "Bengaluru",
             "Electronics", 1.2, 5, 5),
            ("CT10000002", "Meena Reddy", "9700011122", "Hyderabad",
             "Suresh Patil", "9822334455", "Flat 302, Baner Road", "Pune",
             "Document", 0.3, 4, 3),
            ("CT10000003", "Arjun Nair", "9895566778", "Chennai",
             "Lakshmi Rao", "9866778899", "8-2-120, Banjara Hills", "Hyderabad",
             "Clothing", 2.5, 3, 2),
            ("CT10000004", "Pooja Singh", "9910203040", "Delhi",
             "Kiran Varma", "9849505050", "Plot 45, Kukatpally", "Hyderabad",
             "Fragile", 4.0, 3, 2),
            ("CT10000005", "Vijay Gupta", "9833445566", "Mumbai",
             "Sneha Iyer", "9840123456", "22 Anna Salai, T Nagar", "Chennai",
             "Parcel", 3.1, 2, 1),
            ("CT10000006", "Divya Joshi", "9966332211", "Hyderabad",
             "Rahul Mehta", "9820098200", "501 Linking Road, Bandra", "Mumbai",
             "Parcel", 0.8, 1, 0),
        ]
        remarks = {
            "Booked": "Shipment booked at counter",
            "Picked Up": "Parcel collected from sender",
            "In Transit": "On the way to destination hub",
            "Out for Delivery": "With delivery partner",
            "Delivered": "Handed over to receiver",
        }
        now = datetime.now()

        for (tid, s_name, s_phone, origin, r_name, r_phone, address,
             destination, p_type, weight, stages_done, days_ago) in samples:
            booked = now - timedelta(days=days_ago, hours=3)
            cursor = db.execute(
                """INSERT INTO couriers
                   (tracking_id, sender_name, sender_phone, origin, receiver_name,
                    receiver_phone, receiver_address, destination, parcel_type,
                    weight, status, booked_on, expected_delivery)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tid, s_name, s_phone, origin, r_name, r_phone, address,
                 destination, p_type, weight, STATUSES[stages_done - 1],
                 booked.strftime(DATE_FORMAT),
                 (booked + timedelta(days=4)).strftime("%Y-%m-%d")),
            )
            # One history row for every stage the parcel has finished
            for step in range(stages_done):
                status = STATUSES[step]
                location = origin if step < 2 else destination
                if status == "In Transit":
                    location = f"{origin} sorting hub"
                when = booked + (now - booked) * step / stages_done
                db.execute(
                    """INSERT INTO tracking_history
                       (courier_id, status, location, remarks, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cursor.lastrowid, status, location, remarks[status],
                     when.strftime(DATE_FORMAT)),
                )
    db.commit()


# ---------------------------------------------------------------------------
# Small helpers used by the pages
# ---------------------------------------------------------------------------
def admin_required(view):
    """Decorator: only a logged-in admin may open this page."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Log in as admin to open that page.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view


def user_required(view):
    """Decorator: only a logged-in user (customer) may open this page."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("role") != "user":
            flash("Log in to see your parcels.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def check_login(role):
    """Check the submitted username and password for the given role.
    Returns True and starts the session when they are correct."""
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")

    user = get_db().execute(
        "SELECT * FROM users WHERE username = ? AND role = ?", (username, role)
    ).fetchone()

    if user and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"] or user["username"]
        session["role"] = user["role"]
        return True

    flash("Wrong username or password.", "error")
    return False


@app.template_filter("nice_date")
def nice_date(value):
    """Turn '2026-10-05 14:30' into '05 Oct 2026, 02:30 PM'."""
    try:
        if len(value) > 10:
            return datetime.strptime(value, DATE_FORMAT).strftime("%d %b %Y, %I:%M %p")
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return value


@app.context_processor
def share_with_templates():
    """Make these values available inside every HTML template."""
    return {"STATUSES": STATUSES, "PARCEL_TYPES": PARCEL_TYPES}


def get_history(courier_id):
    """All status updates of one courier, newest first."""
    return get_db().execute(
        "SELECT * FROM tracking_history WHERE courier_id = ? ORDER BY id DESC",
        (courier_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Public pages (no login needed)
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/track")
def track():
    """Customer enters a tracking ID and sees where the parcel is."""
    tracking_id = request.args.get("tracking_id", "").strip().upper()
    if not tracking_id:
        flash("Enter a tracking ID to search.", "error")
        return redirect(url_for("home"))

    courier = get_db().execute(
        "SELECT * FROM couriers WHERE tracking_id = ?", (tracking_id,)
    ).fetchone()

    if courier is None:
        flash(f"No courier found with tracking ID {tracking_id}. "
              "Check the ID and try again.", "error")
        return redirect(url_for("home"))

    return render_template(
        "track.html",
        courier=courier,
        history=get_history(courier["id"]),
        current_step=STATUSES.index(courier["status"]),
    )


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page for users (customers)."""
    if request.method == "POST" and check_login("user"):
        return redirect(url_for("my_parcels"))
    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Login page for the admin (courier office staff)."""
    if request.method == "POST" and check_login("admin"):
        return redirect(url_for("dashboard"))
    return render_template("admin_login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Create a new user account."""
    form = {}
    if request.method == "POST":
        form = {key: value.strip() for key, value in request.form.items()}
        full_name = form.get("full_name", "")
        username = form.get("username", "").lower()
        phone = form.get("phone", "")
        password = request.form.get("password", "")
        errors = []

        if not (full_name and username and phone and password):
            errors.append("Fill in every field.")
        if phone and not (phone.isdigit() and len(phone) == 10):
            errors.append("Phone must be exactly 10 digits.")
        if password and len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != request.form.get("confirm_password", ""):
            errors.append("The two passwords do not match.")

        db = get_db()
        if username and db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            errors.append("That username is taken. Choose another one.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            db.execute(
                """INSERT INTO users (username, password_hash, full_name, phone, role)
                   VALUES (?, ?, ?, ?, 'user')""",
                (username, generate_password_hash(password), full_name, phone),
            )
            db.commit()
            flash("Account created. Log in to continue.", "success")
            return redirect(url_for("login"))

    return render_template("signup.html", form=form)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# User pages (user login needed)
# ---------------------------------------------------------------------------
@app.route("/my-parcels")
@user_required
def my_parcels():
    """Every courier sent from or coming to the logged-in user's phone number."""
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()

    if user is None:            # account was removed while logged in
        session.clear()
        return redirect(url_for("login"))

    sent = db.execute(
        "SELECT * FROM couriers WHERE sender_phone = ? ORDER BY id DESC",
        (user["phone"],),
    ).fetchall()
    incoming = db.execute(
        "SELECT * FROM couriers WHERE receiver_phone = ? ORDER BY id DESC",
        (user["phone"],),
    ).fetchall()

    return render_template("my_parcels.html", user=user, sent=sent, incoming=incoming)


# ---------------------------------------------------------------------------
# Admin pages (admin login needed)
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@admin_required
def dashboard():
    """Counts at the top and a searchable list of every courier."""
    db = get_db()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "")

    query = "SELECT * FROM couriers WHERE 1 = 1"
    values = []

    if search:
        query += """ AND (tracking_id LIKE ? OR sender_name LIKE ?
                          OR receiver_name LIKE ? OR destination LIKE ?)"""
        values += [f"%{search}%"] * 4

    if status_filter in STATUSES:
        query += " AND status = ?"
        values.append(status_filter)

    couriers = db.execute(query + " ORDER BY id DESC", values).fetchall()

    # Count couriers in each status for the summary boxes
    counts = {status: 0 for status in STATUSES}
    for row in db.execute("SELECT status, COUNT(*) AS total FROM couriers GROUP BY status"):
        counts[row["status"]] = row["total"]

    stats = {
        "total": sum(counts.values()),
        "waiting": counts["Booked"] + counts["Picked Up"],
        "moving": counts["In Transit"] + counts["Out for Delivery"],
        "delivered": counts["Delivered"],
    }

    return render_template("dashboard.html", couriers=couriers, stats=stats,
                           search=search, status_filter=status_filter)


@app.route("/courier/add", methods=["GET", "POST"])
@admin_required
def add_courier():
    """Book a new courier and give it a tracking ID."""
    default_date = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d")

    if request.method == "POST":
        form = {key: value.strip() for key, value in request.form.items()}
        errors = []

        required = ["sender_name", "sender_phone", "origin", "receiver_name",
                    "receiver_phone", "receiver_address", "destination",
                    "parcel_type", "weight", "expected_delivery"]
        if any(not form.get(field) for field in required):
            errors.append("Fill in every field.")

        for field, label in [("sender_phone", "Sender"), ("receiver_phone", "Receiver")]:
            phone = form.get(field, "")
            if phone and not (phone.isdigit() and len(phone) == 10):
                errors.append(f"{label} phone must be exactly 10 digits.")

        try:
            weight = float(form.get("weight", ""))
            if weight <= 0:
                errors.append("Weight must be more than 0 kg.")
        except ValueError:
            weight = 0
            if form.get("weight"):
                errors.append("Weight must be a number.")

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("add_courier.html", form=form,
                                   default_date=default_date)

        db = get_db()
        tracking_id = generate_tracking_id()
        now = datetime.now().strftime(DATE_FORMAT)

        cursor = db.execute(
            """INSERT INTO couriers
               (tracking_id, sender_name, sender_phone, origin, receiver_name,
                receiver_phone, receiver_address, destination, parcel_type,
                weight, status, booked_on, expected_delivery)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tracking_id, form["sender_name"], form["sender_phone"], form["origin"],
             form["receiver_name"], form["receiver_phone"], form["receiver_address"],
             form["destination"], form["parcel_type"], weight, "Booked", now,
             form["expected_delivery"]),
        )
        # First entry in the parcel's journey
        db.execute(
            """INSERT INTO tracking_history
               (courier_id, status, location, remarks, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (cursor.lastrowid, "Booked", form["origin"], "Shipment booked at counter", now),
        )
        db.commit()

        flash(f"Courier booked. Tracking ID: {tracking_id}", "success")
        return redirect(url_for("courier_detail", courier_id=cursor.lastrowid))

    return render_template("add_courier.html", form={}, default_date=default_date)


@app.route("/courier/<int:courier_id>")
@admin_required
def courier_detail(courier_id):
    """Full details of one courier plus the form to update its status."""
    courier = get_db().execute(
        "SELECT * FROM couriers WHERE id = ?", (courier_id,)
    ).fetchone()

    if courier is None:
        flash("That courier does not exist.", "error")
        return redirect(url_for("dashboard"))

    current_step = STATUSES.index(courier["status"])
    return render_template(
        "courier_detail.html",
        courier=courier,
        history=get_history(courier_id),
        current_step=current_step,
        next_statuses=STATUSES[current_step + 1:],   # a parcel only moves forward
    )


@app.route("/courier/<int:courier_id>/update", methods=["POST"])
@admin_required
def update_status(courier_id):
    """Move the courier to its next stage and record it in the history."""
    db = get_db()
    courier = db.execute(
        "SELECT * FROM couriers WHERE id = ?", (courier_id,)
    ).fetchone()

    if courier is None:
        flash("That courier does not exist.", "error")
        return redirect(url_for("dashboard"))

    new_status = request.form.get("status", "")
    location = request.form.get("location", "").strip()
    remarks = request.form.get("remarks", "").strip()

    allowed = STATUSES[STATUSES.index(courier["status"]) + 1:]

    if new_status not in allowed:
        flash("Choose a status that comes after the current one.", "error")
    elif not location:
        flash("Enter the current location of the parcel.", "error")
    else:
        db.execute("UPDATE couriers SET status = ? WHERE id = ?",
                   (new_status, courier_id))
        db.execute(
            """INSERT INTO tracking_history
               (courier_id, status, location, remarks, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (courier_id, new_status, location, remarks,
             datetime.now().strftime(DATE_FORMAT)),
        )
        db.commit()
        flash(f"Status updated to {new_status}.", "success")

    return redirect(url_for("courier_detail", courier_id=courier_id))


@app.route("/courier/<int:courier_id>/delete", methods=["POST"])
@admin_required
def delete_courier(courier_id):
    db = get_db()
    db.execute("DELETE FROM couriers WHERE id = ?", (courier_id,))
    db.commit()
    flash("Courier deleted.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Start the app
# ---------------------------------------------------------------------------
with app.app_context():
    create_tables()
    add_sample_data()

if __name__ == "__main__":
    app.run(debug=True)
