import pandas as pd
import random

# -------------------- LOAD DATA --------------------
courses = pd.read_csv("data/courses.csv")
rooms = pd.read_csv("data/rooms.csv")
faculty_df = pd.read_csv("data/faculty.csv")

# Faculty availability
faculty_availability = {}
for _, row in faculty_df.iterrows():
    faculty_availability[row["name"]] = row["available_slots"].split(",")

# Convert to list
course_list = courses.to_dict(orient="records")
room_list = rooms.to_dict(orient="records")

# Time slots
time_slots = [
    f"{day}{p}" 
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for p in range(1, 9)
]

# -------------------- FITNESS FUNCTION --------------------
def fitness(timetable):
    score = 100

    for i in range(len(timetable)):
        for j in range(i + 1, len(timetable)):

            if timetable[i]["slot"] == timetable[j]["slot"]:

                # Faculty clash
                if timetable[i]["faculty"] == timetable[j]["faculty"]:
                    score -= 20

                # Room clash
                if timetable[i]["room"] == timetable[j]["room"]:
                    score -= 20

                # NEP elective clash
                if timetable[i]["type"] == "elective" and timetable[j]["type"] == "elective":
                    score -= 15

        # Faculty availability
        faculty = timetable[i]["faculty"]
        slot = timetable[i]["slot"]

        if slot not in faculty_availability.get(faculty, []):
            score -= 10

    return score

# -------------------- RANDOM TIMETABLE --------------------
def generate_random_timetable():
    timetable = []

    for course in course_list:
        faculty = course["faculty"]

        valid_slots = faculty_availability.get(faculty, time_slots)

        slot = random.choice(valid_slots)
        room = random.choice(room_list)

        timetable.append({
            "course": course["course_name"],
            "faculty": faculty,
            "slot": slot,
            "room": room["room_name"],
            "type": course["type"]
        })

    return timetable

# -------------------- SELECTION --------------------
def selection(population):
    population = sorted(population, key=fitness, reverse=True)
    return population[:10]

# -------------------- CROSSOVER --------------------
def crossover(parent1, parent2):
    child = []

    for i in range(len(parent1)):
        if random.random() > 0.5:
            child.append(parent1[i].copy())
        else:
            child.append(parent2[i].copy())

    return child

# -------------------- MUTATION --------------------
def mutate(timetable):
    t = random.choice(timetable)

    t["slot"] = random.choice(time_slots)
    t["room"] = random.choice(room_list)["room_name"]

    return timetable

# -------------------- INITIAL POPULATION --------------------
population = [generate_random_timetable() for _ in range(50)]

# -------------------- GENETIC ALGORITHM --------------------
generations = 100

for gen in range(generations):

    selected = selection(population)
    new_population = selected.copy()

    while len(new_population) < 50:
        parent1 = random.choice(selected)
        parent2 = random.choice(selected)

        child = crossover(parent1, parent2)

        if random.random() < 0.2:
            child = mutate(child)

        new_population.append(child)

    population = new_population

    best_score = max([fitness(p) for p in population])
    print(f"Generation {gen} Best Score: {best_score}")

# -------------------- BEST RESULT --------------------
best_timetable = max(population, key=fitness)

print("\nFinal Optimized Timetable:\n")

for t in best_timetable:
    day = t['slot'][:3]
    period = t['slot'][3:]
    print(f"{day} Period {period} -> {t['course']} | {t['faculty']} | {t['room']}")

    # -------------------- GRID FORMAT --------------------
days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
periods = [str(i) for i in range(1, 9)]

# Create empty grid
grid = {day: {p: "Free" for p in periods} for day in days}
for d in days:
    grid[d]["4"] = "LUNCH BREAK 🍱"
# Fill grid with timetable
for t in best_timetable:
    day = t["slot"][:3]
    period = t["slot"][3:]

    grid[day][period] = f"{t['course']} ({t['room']})"

# Convert to DataFrame for nice display
grid_df = pd.DataFrame(grid).T

print("\nTimetable Grid:\n")
print(grid_df)