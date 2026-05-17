import asyncio
import threading
import requests
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, abort,
)
from config import SECRET_KEY
from models import (
    create_user, get_user, hash_password,
    update_user_login, log_login_attempt,
)
from pcloud import list_folder, get_download_link, humanbytes
from bot import send_registration_alert, send_login_alert, run_bot_background

app = Flask(__name__)
app.secret_key = SECRET_KEY


# =====================================================
# HELPERS
# =====================================================

def get_client_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr


def get_browser_info(ua_string):
    if not ua_string:
        return "Unknown", "Unknown", "Unknown"

    browser = "Unknown"
    os_name = "Unknown"
    device = "Desktop"

    ua = ua_string.lower()

    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    elif "opera" in ua or "opr" in ua:
        browser = "Opera"

    if "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    elif "android" in ua:
        os_name = "Android"
        device = "Mobile"
    elif "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
        device = "Mobile"

    return browser, os_name, device


def get_location(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        data = r.json()
        if data.get("status") == "success":
            return f"{data.get('city', '')}, {data.get('country', '')}"
    except:
        pass
    return "Unknown"


def send_tg_alert(coro):
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(coro)
        loop.close()
        print("[TG] Alert sent successfully")
    except Exception as e:
        print(f"[TG] Alert error: {e}")


# =====================================================
# AUTH MIDDLEWARE
# =====================================================

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("files"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        existing = get_user(email)
        if existing:
            flash("Email already registered. Wait for approval.", "info")
            return render_template("register.html")

        ip = get_client_ip()
        ua = request.headers.get("User-Agent", "")
        browser, os_name, device = get_browser_info(ua)
        location = get_location(ip)

        create_user(email, password, ip, ua, browser, os_name, device, location)
        print(f"[REG] New user: {email} | IP: {ip} | {browser} on {os_name}")

        send_tg_alert(
            send_registration_alert(email, ip, browser, os_name, device, location)
        )

        flash("Registration submitted! Wait for admin approval.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user(email)

        if not user or user["password_hash"] != hash_password(password):
            ip = get_client_ip()
            ua = request.headers.get("User-Agent", "")
            browser, os_name, device = get_browser_info(ua)
            location = get_location(ip)

            log_login_attempt(
                email, ip, ua, browser, os_name, device, location,
                "failed", "Wrong credentials"
            )
            print(f"[LOGIN] FAILED: {email} | IP: {ip}")

            send_tg_alert(
                send_login_alert(
                    email, ip, browser, os_name, device, location,
                    "Wrong credentials"
                )
            )

            flash("Invalid email or password.", "error")
            return render_template("login.html")

        if user["status"] == "pending":
            flash("Your account is pending approval.", "info")
            return render_template("login.html")

        if user["status"] == "denied":
            flash("Your account has been denied.", "error")
            return render_template("login.html")

        ip = get_client_ip()
        ua = request.headers.get("User-Agent", "")
        browser, os_name, device = get_browser_info(ua)
        location = get_location(ip)

        stored_ip = user["ip_address"]
        stored_ua = user["user_agent"]

        is_new_ip = stored_ip and stored_ip != ip
        is_new_device = stored_ua and stored_ua != ua

        if is_new_ip or is_new_device:
            reason = []
            if is_new_ip:
                reason.append(f"New IP (was {stored_ip})")
            if is_new_device:
                reason.append("New device")
            reason_str = " + ".join(reason)

            log_login_attempt(
                email, ip, ua, browser, os_name, device, location,
                "blocked", reason_str
            )
            print(f"[LOGIN] BLOCKED: {email} | {reason_str}")

            send_tg_alert(
                send_login_alert(
                    email, ip, browser, os_name, device, location, reason_str
                )
            )

            flash("New device/IP detected. Admin approval required.", "info")
            return render_template("login.html")

        update_user_login(email, ip, ua, browser, os_name, device, location)
        print(f"[LOGIN] SUCCESS: {email} | IP: {ip} | {browser} on {os_name}")

        send_tg_alert(
            send_login_alert(
                email, ip, browser, os_name, device, location,
                "Successful login"
            )
        )

        session["user"] = email
        return redirect(url_for("files"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


@app.route("/files/")
@app.route("/files/<path:subpath>")
@login_required
def files(subpath=""):
    if not subpath.startswith("/"):
        subpath = "/" + subpath

    result = list_folder(subpath)

    if "error" in result:
        flash(f"Error: {result['error']}", "error")

    breadcrumbs = []
    if subpath and subpath != "/":
        parts = subpath.strip("/").split("/")
        for i, part in enumerate(parts):
            breadcrumbs.append({
                "name": part,
                "path": "/" + "/".join(parts[: i + 1]),
            })

    return render_template(
        "files.html",
        folders=result.get("folders", []),
        files=result.get("files", []),
        current_path=subpath,
        breadcrumbs=breadcrumbs,
        humanbytes=humanbytes,
    )


@app.route("/download/<path:filepath>")
@login_required
def download(filepath):
    link = get_download_link("/" + filepath)
    if not link:
        abort(404)

    return redirect(link)


# =====================================================
# START
# =====================================================

if __name__ == "__main__":
    print("[BOT] Starting Telegram bot...")
    bot_thread = threading.Thread(target=run_bot_background, daemon=True)
    bot_thread.start()

    print("[APP] Starting Flask server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)
