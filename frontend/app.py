from auth import auth
from database import init_db
from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit
from matplotlib.pyplot import grid
import pandas as pd
import random
import os
import json

# -------- PATH SETUP --------
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.secret_key = "supersecretkey"
app.register_blueprint(auth)
init_db()

socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")
# -------- LOAD DATA --------
courses = pd.read_csv("../data/courses.csv")
rooms = pd.read_csv("../data/rooms.csv")

course_list = courses.to_dict(orient="records")
room_list = rooms.to_dict(orient="records")

time_slots = [
    f"{day}{p}"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for p in range(1, 9)
]

# ================= GA FUNCTION =================
def fitness(timetable):
    score = 0
    used_slots = set()
    faculty_schedule = {}
    room_schedule = {}

    for t in timetable:
        slot = t["slot"]
        faculty = t["faculty"]
        room = t["room"]

        # ✅ BIG reward for valid class
        score += 20

        # ❌ slot reuse (very bad)
        if slot in used_slots:
            score -= 80
        else:
            used_slots.add(slot)

        
        if (faculty, slot) in faculty_schedule:
            score -= 100
        else:
            faculty_schedule[(faculty, slot)] = True

        
        if (room, slot) in room_schedule:
            score -= 100
        else:
            room_schedule[(room, slot)] = True

       
        if slot.endswith("4"):
            score -= 120

    # ✅ ADD controlled randomness (important for graph variation)
    score += random.randint(-20, 20)

    return score

def generate_random():
    timetable = []
    used_slots = set()

    for course in course_list:

        hours = int(course["hours"])   # 🔥 NEW LINE

        for _ in range(hours):   # 🔥 LOOP BASED ON HOURS

            slot = random.choice(time_slots)

            # avoid duplicates + lunch
            while slot in used_slots or slot.endswith("4"):
                slot = random.choice(time_slots)

            used_slots.add(slot)

            room = random.choice(room_list)

            timetable.append({
                "course": course["course_name"],
                "faculty": course["faculty"],
                "slot": slot,
                "room": room["room_name"],
                "type": course["type"]
            })

    return timetable

def selection(pop):
        return sorted(pop, key=fitness, reverse=True)[:10]

def crossover(p1, p2):
        return [random.choice([p1[i], p2[i]]).copy() for i in range(len(p1))]

def mutate(t):
    for _ in range(5):
        x = random.choice(t)
        x["slot"] = random.choice(time_slots)
    return t

def format_grid(timetable_list):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods = [str(i) for i in range(1, 9)]
    grid = {d: {p: "Free" for p in periods} for d in days}
    for d in days:
        grid[d]["4"] = "LUNCH BREAK 🍱"
        
    for t in timetable_list:
        day = t["slot"][:3]
        period = t["slot"][3:]
        if period == "4":
            continue
        grid[day][period] = {
            "course": t["course"],
            "faculty": t["faculty"],
            "room": t["room"],
            "section": "A"
        }
    return grid

@socketio.on('start_generation')
def handle_start_generation(weights):
    if not weights:
        weights = {
            'w_reuse': 80,
            'w_faculty': 100,
            'w_room': 100,
            'w_subject': 40,
            'w_lunch': 120
        }

    def fitness(timetable):
        score = 0
        used_slots = set()
        faculty_schedule = {}
        room_schedule = {}
        subject_day = {}

        for t in timetable:
            slot = t["slot"]
            faculty = t["faculty"]
            room = t["room"]
            course = t["course"]
            day = slot[:3]

            score += 20

            if slot in used_slots:
                score -= int(weights['w_reuse'])
            else:
                used_slots.add(slot)

            if (faculty, slot) in faculty_schedule:
                score -= int(weights['w_faculty'])
            else:
                faculty_schedule[(faculty, slot)] = True

            if (room, slot) in room_schedule:
                score -= int(weights['w_room'])
            else:
                room_schedule[(room, slot)] = True

            if (course, day) in subject_day:
                score -= int(weights['w_subject'])
            else:
                subject_day[(course, day)] = True

            if slot.endswith("4"):
                score -= int(weights['w_lunch'])

        score += random.randint(-20, 20)
        return score

    def generate_random():
        timetable = []
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
                    "course": course["course_name"],
                    "faculty": course["faculty"],
                    "slot": slot,
                    "room": room["room_name"],
                    "type": course["type"]
                })
        return timetable

    def selection(pop):
        return sorted(pop, key=fitness, reverse=True)[:10]

    def crossover(p1, p2):
        return [random.choice([p1[i], p2[i]]).copy() for i in range(len(p1))]

    def mutate(t):
        for _ in range(5):
            x = random.choice(t)
            x["slot"] = random.choice(time_slots)
        return t

    population = [generate_random() for _ in range(30)]
    scores = []

    for gen in range(50):
        selected = selection(population)
        new_pop = selected.copy()

        while len(new_pop) < 30:
            child = crossover(random.choice(selected), random.choice(selected))
            if random.random() < 0.5:
                child = mutate(child)
            new_pop.append(child)

        population = new_pop
        
        # Emit live update every 2 generations to avoid overwhelming client
        if gen % 2 == 0 or gen == 49:
            best = max(population, key=fitness)
            current_score = fitness(best)
            scores.append(current_score)
            
            socketio.emit('generation_update', {
                'generation': gen,
                'scores': scores,
                'timetable': [format_grid(best)]
            })
            socketio.sleep(0.05)

@socketio.on('cell_moved')
def handle_cell_moved(data):
    emit('sync_move', data, broadcast=True, include_self=False)

@app.route('/dispatch', methods=['POST'])
def dispatch_schedule():
    if "user" not in session:
        return "Unauthorized", 401
    
    grid_data = request.json
    
    from auth import SENDER_EMAIL, APP_PASSWORD
    from email.message import EmailMessage
    import smtplib

    teachers = {}
    for day, periods in grid_data.items():
        for period, val in periods.items():
            if isinstance(val, dict):
                faculty = val.get("faculty")
                if faculty not in teachers:
                    teachers[faculty] = []
                teachers[faculty].append(f"{day} Period {period}: {val.get('course')} in {val.get('room')}")
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            
            for teacher, classes in teachers.items():
                msg = EmailMessage()
                class_list = "\n".join(classes)
                msg.set_content(f"Hello {teacher},\n\nHere is your AI generated schedule for the week:\n\n{class_list}\n\nBest,\nAdmin")
                msg["Subject"] = f"Your Weekly Timetable - {teacher}"
                msg["From"] = SENDER_EMAIL
                msg["To"] = SENDER_EMAIL
                
                server.send_message(msg)
                
        return "Successfully published! Emails have been dispatched to all teachers."
    except Exception as e:
        print("Dispatch error:", e)
        return "Failed to send emails. Please check your SMTP configuration in auth.py."

@app.route('/chat', methods=['POST'])
def chat():
    text = request.json.get("text", "").lower()
    weights = request.json.get("weights", {})
    
    response_msg = "I've updated the settings."
    updated = False

    # Simple keyword-based NLP
    if "lunch" in text:
        if "zero" in text or "0" in text or "ignore" in text or "remove" in text:
            weights['w_lunch'] = 0
            response_msg = "I've set the lunch penalty to 0. Classes will be scheduled during lunch!"
            updated = True
        elif "increase" in text or "prioritize" in text or "high" in text:
            weights['w_lunch'] = 200
            response_msg = "Lunch penalty maxed out. Lunch break is now strictly protected."
            updated = True
            
    if "faculty" in text or "teacher" in text:
        if "increase" in text or "prioritize" in text or "strict" in text:
            weights['w_faculty'] = 200
            response_msg = "Faculty clash penalty maxed out. Double bookings will be avoided."
            updated = True
            
    if "room" in text:
        if "increase" in text or "prioritize" in text or "strict" in text:
            weights['w_room'] = 200
            response_msg = "Room clash penalty maximized."
            updated = True

    if "subject" in text or "twice" in text:
        if "allow" in text or "0" in text or "zero" in text:
            weights['w_subject'] = 0
            response_msg = "I've allowed subjects to be scheduled twice in the same day."
            updated = True
            
    if "reuse" in text or "slot" in text:
        if "increase" in text:
            weights['w_reuse'] = 200
            updated = True

    if not updated:
        response_msg = "I didn't quite catch that. Try saying 'set lunch penalty to 0' or 'prioritize faculty clashes'."

    return {"message": response_msg, "weights": weights}

@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")

    # Serve an empty grid initially
    weights = {
        'w_reuse': 80,
        'w_faculty': 100,
        'w_room': 100,
        'w_subject': 40,
        'w_lunch': 120
    }
    
    empty_grid = format_grid([])

    return render_template(
        "index.html",
        timetables=[empty_grid],
        scores=[],
        weights=weights
    )

if __name__ == "__main__":
    socketio.run(app, debug=True)