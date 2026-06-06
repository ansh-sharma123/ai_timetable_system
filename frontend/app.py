"""
ChronoGen — Main Application (Phase 1 + Phase 2 Upgrade)
• GA runs in a dedicated background thread (cancellable)
• /validate endpoint for real-time drag-and-drop conflict checking
• /analytics endpoint for diagnostics dashboard data
• /export_ical endpoint for calendar export
"""
from auth import auth
from database import init_db
from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit
import pandas as pd
import random
import os
import json
import threading

# ─── PATH SETUP ──────────────────────────────────────────────────────────────
base_dir     = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.environ.get("SECRET_KEY", "chronogen-secret-key-change-in-prod")
app.register_blueprint(auth)
init_db()

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ─── LOAD DATA ───────────────────────────────────────────────────────────────
courses   = pd.read_csv(os.path.join(base_dir, "../data/courses.csv"))
rooms     = pd.read_csv(os.path.join(base_dir, "../data/rooms.csv"))

course_list = courses.to_dict(orient="records")
room_list   = rooms.to_dict(orient="records")

time_slots = [
    f"{day}{p}"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for p in range(1, 9)
]

# ─── GA CANCELLATION FLAG ────────────────────────────────────────────────────
# Each user session gets a flag. When they click Generate again, the previous
# GA thread is signalled to stop.
_ga_cancel_flags: dict[str, threading.Event] = {}


# ─── GA HELPERS ──────────────────────────────────────────────────────────────
def _fitness(timetable: list, weights: dict) -> int:
    score = 0
    used_slots     = set()
    faculty_sched  = {}
    room_sched     = {}
    subject_day    = {}

    for t in timetable:
        slot    = t["slot"]
        faculty = t["faculty"]
        room    = t["room"]
        course  = t["course"]
        day     = slot[:3]

        score += 20

        if slot in used_slots:
            score -= int(weights["w_reuse"])
        else:
            used_slots.add(slot)

        if (faculty, slot) in faculty_sched:
            score -= int(weights["w_faculty"])
        else:
            faculty_sched[(faculty, slot)] = True

        if (room, slot) in room_sched:
            score -= int(weights["w_room"])
        else:
            room_sched[(room, slot)] = True

        if (course, day) in subject_day:
            score -= int(weights["w_subject"])
        else:
            subject_day[(course, day)] = True

        if slot.endswith("4"):
            score -= int(weights["w_lunch"])

    score += random.randint(-20, 20)
    return score


def _generate_random() -> list:
    timetable  = []
    used_slots = set()
    for course in course_list:
        hours = int(course["hours"])
        for _ in range(hours):
            slot = random.choice(time_slots)
            while slot in used_slots or slot.endswith("4"):
                slot = random.choice(time_slots)
            used_slots.add(slot)
            room = random.choice(room_list)
            timetable.append({
                "course":  course["course_name"],
                "faculty": course["faculty"],
                "slot":    slot,
                "room":    room["room_name"],
                "type":    course["type"],
            })
    return timetable


def _crossover(p1: list, p2: list) -> list:
    return [random.choice([p1[i], p2[i]]).copy() for i in range(len(p1))]


def _mutate(t: list) -> list:
    for _ in range(5):
        x = random.choice(t)
        x["slot"] = random.choice(time_slots)
    return t


def format_grid(timetable_list: list) -> dict:
    days    = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods = [str(i) for i in range(1, 9)]
    grid    = {d: {p: "Free" for p in periods} for d in days}
    for d in days:
        grid[d]["4"] = "LUNCH BREAK 🍱"
    for t in timetable_list:
        day    = t["slot"][:3]
        period = t["slot"][3:]
        if period == "4":
            continue
        grid[day][period] = {
            "course":  t["course"],
            "faculty": t["faculty"],
            "room":    t["room"],
            "section": "A",
        }
    return grid


def _compute_conflicts(timetable_list: list) -> dict:
    """Return a dict of slot -> conflict_level (none/soft/hard)."""
    faculty_slots: dict = {}
    room_slots: dict    = {}
    subject_days: dict  = {}
    conflicts           = {}

    for t in timetable_list:
        slot    = t["slot"]
        faculty = t["faculty"]
        room    = t["room"]
        course  = t["course"]
        day     = slot[:3]
        level   = "none"

        if (faculty, slot) in faculty_slots:
            level = "hard"
        faculty_slots[(faculty, slot)] = True

        if (room, slot) in room_slots:
            level = "hard"
        room_slots[(room, slot)] = True

        if (course, day) in subject_days:
            level = "soft" if level == "none" else level
        subject_days[(course, day)] = True

        conflicts[slot] = level

    return conflicts


def _run_ga(sid: str, weights: dict, cancel_event: threading.Event):
    """The actual GA loop — runs in its own thread."""
    fitness_fn = lambda tt: _fitness(tt, weights)
    population = [_generate_random() for _ in range(30)]
    scores     = []

    for gen in range(50):
        if cancel_event.is_set():
            break

        selected = sorted(population, key=fitness_fn, reverse=True)[:10]
        new_pop  = selected.copy()

        while len(new_pop) < 30:
            child = _crossover(random.choice(selected), random.choice(selected))
            if random.random() < 0.5:
                child = _mutate(child)
            new_pop.append(child)

        population = new_pop

        if gen % 2 == 0 or gen == 49:
            best          = max(population, key=fitness_fn)
            current_score = fitness_fn(best)
            scores.append(current_score)
            conflicts     = _compute_conflicts(best)

            socketio.emit("generation_update", {
                "generation": gen,
                "total":      49,
                "scores":     scores,
                "timetable":  [format_grid(best)],
                "conflicts":  conflicts,
            }, room=sid)
            socketio.sleep(0.05)

    # Signal completion
    if not cancel_event.is_set():
        socketio.emit("generation_done", {"message": "✅ Timetable generation complete!"}, room=sid)


# ─── SOCKET EVENTS ───────────────────────────────────────────────────────────
@socketio.on("start_generation")
def handle_start_generation(weights):
    sid = request.sid
    if not weights:
        weights = {"w_reuse": 80, "w_faculty": 100, "w_room": 100, "w_subject": 40, "w_lunch": 120}

    # Cancel any running GA for this session
    if sid in _ga_cancel_flags:
        _ga_cancel_flags[sid].set()

    cancel_event = threading.Event()
    _ga_cancel_flags[sid] = cancel_event

    t = threading.Thread(target=_run_ga, args=(sid, weights, cancel_event), daemon=True)
    t.start()


@socketio.on("cell_moved")
def handle_cell_moved(data):
    emit("sync_move", data, broadcast=True, include_self=False)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    if sid in _ga_cancel_flags:
        _ga_cancel_flags[sid].set()
        del _ga_cancel_flags[sid]


# ─── REST ENDPOINTS ──────────────────────────────────────────────────────────
@app.route("/validate", methods=["POST"])
def validate_move():
    """
    Called by the frontend when user drags a card.
    Body: { source_slot, target_slot, timetable_grid }
    Returns: { status: 'valid'|'soft'|'hard', reason: str }
    """
    data        = request.json or {}
    target_slot = data.get("target_slot", "")
    grid        = data.get("grid", {})

    # Check if target slot is lunch break
    if target_slot.endswith("4"):
        return jsonify({"status": "hard", "reason": "Cannot schedule during lunch break (Period 4)."})

    day    = target_slot[:3]
    period = target_slot[3:]

    if day not in grid or period not in grid[day]:
        return jsonify({"status": "valid", "reason": "Slot is free."})

    cell = grid[day].get(period)
    if not cell or cell in ("Free", "LUNCH BREAK 🍱"):
        return jsonify({"status": "valid", "reason": "Slot is free."})

    moving_faculty = data.get("faculty", "")
    target_faculty = cell.get("faculty", "")
    moving_room    = data.get("room", "")
    target_room    = cell.get("room", "")

    if moving_faculty and moving_faculty == target_faculty:
        return jsonify({"status": "hard", "reason": f"{moving_faculty} already has a class at this time."})

    if moving_room and moving_room == target_room:
        return jsonify({"status": "soft", "reason": f"Room {moving_room} is occupied but can be swapped."})

    return jsonify({"status": "soft", "reason": "Slot occupied — cells will swap."})


@app.route("/analytics")
def analytics():
    """Returns room utilization and faculty workload data."""
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    total_slots   = 5 * 7  # 5 days × 7 teaching periods
    course_count  = {}
    faculty_count = {}

    for c in course_list:
        faculty = c["faculty"]
        faculty_count[faculty] = faculty_count.get(faculty, 0) + int(c["hours"])
        course_count[c["course_name"]] = int(c["hours"])

    return jsonify({
        "total_teaching_slots": total_slots,
        "total_course_hours":   sum(int(c["hours"]) for c in course_list),
        "faculty_workload":     faculty_count,
        "course_hours":         course_count,
        "rooms":                [r["room_name"] for r in room_list],
    })


@app.route("/export_ical")
def export_ical():
    """Export the last generated timetable as an iCal .ics string (stub)."""
    if "user" not in session:
        return "Unauthorized", 401
    ical = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//ChronoGen//EN\r\n"
        "X-WR-CALNAME:ChronoGen Timetable\r\nEND:VCALENDAR\r\n"
    )
    return ical, 200, {
        "Content-Type":        "text/calendar; charset=utf-8",
        "Content-Disposition": "attachment; filename=timetable.ics",
    }


@app.route("/dispatch", methods=["POST"])
def dispatch_schedule():
    if "user" not in session:
        return "Unauthorized", 401

    grid_data = request.json
    from auth import SENDER_EMAIL, APP_PASSWORD
    import smtplib
    from email.message import EmailMessage

    teachers: dict = {}
    for day, periods in grid_data.items():
        for period, val in periods.items():
            if isinstance(val, dict):
                faculty = val.get("faculty")
                if faculty not in teachers:
                    teachers[faculty] = []
                teachers[faculty].append(
                    f"{day} Period {period}: {val.get('course')} in {val.get('room')}"
                )

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            for teacher, classes in teachers.items():
                msg = EmailMessage()
                class_list = "\n".join(classes)
                msg.set_content(
                    f"Hello {teacher},\n\nHere is your AI-generated schedule for the week:\n\n"
                    f"{class_list}\n\nBest,\nChronoGen Admin"
                )
                msg["Subject"] = f"Your Weekly Timetable — {teacher}"
                msg["From"]    = SENDER_EMAIL
                msg["To"]      = SENDER_EMAIL
                server.send_message(msg)
        return "✅ Schedule published! Emails dispatched to all teachers."
    except Exception as e:
        print("Dispatch error:", e)
        return "❌ Failed to send emails. Check your SMTP config.", 500


@app.route("/chat", methods=["POST"])
def chat():
    text    = request.json.get("text", "").lower()
    weights = request.json.get("weights", {})
    response_msg = "I've updated the settings."
    updated = False

    if "lunch" in text:
        if any(k in text for k in ("zero", "0", "ignore", "remove")):
            weights["w_lunch"] = 0
            response_msg = "Lunch penalty set to 0. Classes can now be scheduled during lunch!"
            updated = True
        elif any(k in text for k in ("increase", "prioritize", "high", "strict")):
            weights["w_lunch"] = 200
            response_msg = "Lunch penalty maxed — lunch break is strictly protected."
            updated = True

    if any(k in text for k in ("faculty", "teacher")):
        if any(k in text for k in ("increase", "prioritize", "strict")):
            weights["w_faculty"] = 200
            response_msg = "Faculty clash penalty maxed — double-bookings avoided."
            updated = True

    if "room" in text:
        if any(k in text for k in ("increase", "prioritize", "strict")):
            weights["w_room"] = 200
            response_msg = "Room clash penalty maximized."
            updated = True

    if any(k in text for k in ("subject", "twice")):
        if any(k in text for k in ("allow", "0", "zero")):
            weights["w_subject"] = 0
            response_msg = "Subjects can now be scheduled twice in the same day."
            updated = True

    if any(k in text for k in ("reuse", "slot")):
        if "increase" in text:
            weights["w_reuse"] = 200
            updated = True

    if not updated:
        response_msg = (
            "I didn't quite catch that. Try: "
            "\"set lunch penalty to 0\", \"prioritize faculty clashes\", "
            "\"strict room constraints\"."
        )

    return jsonify({"message": response_msg, "weights": weights})


@app.route("/add_subject", methods=["POST"])
def add_subject():
    if "user" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data        = request.json
    course_name = data.get("course_name")
    faculty     = data.get("faculty")
    hours       = data.get("hours")
    course_type = data.get("type", "core")

    if not all([course_name, faculty, hours]):
        return jsonify({"success": False, "message": "Missing required fields."}), 400

    try:
        max_id  = max((int(c.get("course_id", 0)) for c in course_list), default=0)
        new_id  = max_id + 1
    except Exception:
        new_id  = len(course_list) + 1

    new_course = {
        "course_id":   new_id,
        "course_name": course_name,
        "faculty":     faculty,
        "hours":       int(hours),
        "type":        course_type,
    }
    course_list.append(new_course)

    csv_path = os.path.join(base_dir, "../data/courses.csv")
    try:
        pd.DataFrame([new_course]).to_csv(csv_path, mode="a", header=False, index=False)
        return jsonify({"success": True, "message": f"Subject '{course_name}' added successfully!"})
    except Exception as e:
        print("Error saving subject:", e)
        return jsonify({"success": False, "message": "Failed to save subject."}), 500


@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")

    weights    = {"w_reuse": 80, "w_faculty": 100, "w_room": 100, "w_subject": 40, "w_lunch": 120}
    empty_grid = format_grid([])

    return render_template(
        "index.html",
        timetables=[empty_grid],
        scores=[],
        weights=weights,
        user=session["user"],
    )


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)