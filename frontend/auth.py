# pyrefly: ignore [missing-import]
from flask import Blueprint, render_template, request, redirect, session
import random
import smtplib
import os
from email.message import EmailMessage
from database import create_user, check_user, get_user_by_email, update_password

auth = Blueprint("auth", __name__)

# -------- SIGNUP --------
@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if get_user_by_email(email):
            return "User already exists!"

        success = create_user(email, password)
        if not success:
            return "Error creating user!"

        return redirect("/login")

    return render_template("signup.html")


# -------- LOGIN --------
@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = check_user(email, password)

        if user:
            session["user"] = email
            return redirect("/")

        return "Invalid credentials!"

    return render_template("login.html")


# -------- LOGOUT --------
@auth.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


# -------- FORGOT PASSWORD FLOW --------

# Load credentials from environment variables (recommended for production)
# Set SENDER_EMAIL and APP_PASSWORD as environment variables, or they fall back to defaults
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "anshul3478@gmail.com")
APP_PASSWORD  = os.environ.get("APP_PASSWORD",  "alzvnyspohrbdeka")

# Temporary storage for reset codes (in production, use a database or Redis with expiration)
reset_codes = {}

@auth.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        
        # We no longer check if the email exists. We will allow ANY email to receive a code.

        # Generate a 6-digit random code
        code = str(random.randint(100000, 999999))
        reset_codes[email] = code

        # SENDING REAL EMAIL
        try:
            msg = EmailMessage()
            msg.set_content(f"Your ChronoGen verification code is: {code}\n\nPlease enter this code to reset your password.")
            msg["Subject"] = "Password Reset Verification Code"
            msg["From"] = SENDER_EMAIL
            msg["To"] = email

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, APP_PASSWORD)
                server.send_message(msg)
                
            print(f"[OK] Successfully sent verification email to {email}")
        except Exception as e:
            print(f"[!!] Failed to send email: {e}")
            return f"Failed to send email. Please check your SMTP settings in auth.py."

        # Save email in session temporarily for the next step
        session["reset_email"] = email
        return redirect("/verify_code")

    return render_template("forgot_password.html")


@auth.route("/verify_code", methods=["GET", "POST"])
def verify_code():
    if "reset_email" not in session:
        return redirect("/forgot_password")
        
    email = session["reset_email"]

    if request.method == "POST":
        entered_code = request.form["code"]
        
        if email in reset_codes and reset_codes[email] == entered_code:
            # Code verified, allow password reset
            return redirect("/reset_password")
        else:
            return "Invalid verification code!"

    return render_template("verify_code.html", email=email)


@auth.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if "reset_email" not in session:
        return redirect("/forgot_password")
        
    email = session["reset_email"]

    if request.method == "POST":
        new_password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            return "Passwords do not match!"

        user = get_user_by_email(email)
        
        if user:
            # Update the password
            success = update_password(email, new_password)
        else:
            # Create a new user if they didn't exist
            success = create_user(email, new_password)

        if not success:
            return "Failed to save password."

        # Cleanup
        reset_codes.pop(email, None)
        session.pop("reset_email", None)

        return redirect("/login")

    return render_template("reset_password.html", email=email)