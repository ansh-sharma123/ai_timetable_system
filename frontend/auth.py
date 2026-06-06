"""
ChronoGen — Auth Blueprint (Phase 1 Upgrade)
Password reset now uses secure, expiring URL tokens stored in the database
instead of in-memory 6-digit codes.
"""
# pyrefly: ignore [missing-import]
from flask import Blueprint, render_template, request, redirect, session, url_for
import os
import smtplib
from email.message import EmailMessage
from database import (
    create_user, check_user, get_user_by_email, update_password,
    create_reset_token, verify_reset_token, consume_reset_token
)

auth = Blueprint("auth", __name__)

# ─── SMTP credentials (loaded from environment / .env) ───────────────────────
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "anshul3478@gmail.com")
APP_PASSWORD  = os.environ.get("APP_PASSWORD",  "alzvnyspohrbdeka")


# ─── Helper ──────────────────────────────────────────────────────────────────
def _send_email(to: str, subject: str, body: str) -> bool:
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"]    = SENDER_EMAIL
        msg["To"]      = to
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[SMTP Error] {e}")
        return False


# ─── Signup ──────────────────────────────────────────────────────────────────
@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        if get_user_by_email(email):
            return render_template("signup.html", error="An account with this email already exists.")

        if not create_user(email, password):
            return render_template("signup.html", error="Could not create account. Please try again.")

        return redirect("/login")

    return render_template("signup.html")


# ─── Login ───────────────────────────────────────────────────────────────────
@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        user = check_user(email, password)
        if user:
            session["user"] = email
            return redirect("/")

        return render_template("login.html", error="Invalid email or password.")

    return render_template("login.html")


# ─── Logout ──────────────────────────────────────────────────────────────────
@auth.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


# ─── Forgot Password — Step 1: enter email ───────────────────────────────────
@auth.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]

        # Always generate a token (don't reveal whether email exists = anti-enumeration)
        token = create_reset_token(email)

        # Build a secure reset link
        reset_link = url_for("auth.reset_password_token", token=token, _external=True)

        body = (
            f"Hello,\n\n"
            f"A password reset was requested for your ChronoGen account ({email}).\n\n"
            f"Click the link below to set a new password. "
            f"This link expires in 30 minutes.\n\n"
            f"  {reset_link}\n\n"
            f"If you did not request this, you can safely ignore this email.\n\n"
            f"— ChronoGen System"
        )

        sent = _send_email(email, "ChronoGen — Password Reset", body)
        if not sent:
            return render_template(
                "forgot_password.html",
                error="Failed to send email. Please check your SMTP settings."
            )

        return render_template(
            "forgot_password.html",
            success=f"Reset link sent to {email}. Check your inbox (expires in 30 min)."
        )

    return render_template("forgot_password.html")


# ─── Reset Password — Step 2: token link from email ──────────────────────────
@auth.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password_token(token: str):
    email = verify_reset_token(token)
    if not email:
        return render_template(
            "reset_password.html",
            error="This reset link is invalid or has expired. Please request a new one.",
            token=None
        )

    if request.method == "POST":
        new_password     = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            return render_template("reset_password.html", error="Passwords do not match.", token=token)

        if len(new_password) < 8:
            return render_template("reset_password.html", error="Password must be at least 8 characters.", token=token)

        # Create or update the user
        if get_user_by_email(email):
            success = update_password(email, new_password)
        else:
            success = create_user(email, new_password)

        if not success:
            return render_template("reset_password.html", error="Failed to save password. Try again.", token=token)

        consume_reset_token(token)
        return redirect("/login")

    return render_template("reset_password.html", email=email, token=token)


# ─── Legacy verify_code route — redirect to new flow ─────────────────────────
@auth.route("/verify_code", methods=["GET", "POST"])
def verify_code():
    return redirect("/forgot_password")


# ─── Legacy reset_password route — redirect to new flow ──────────────────────
@auth.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    return redirect("/forgot_password")