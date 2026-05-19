import pandas as pd
import random

# -------------------- LOAD DATA --------------------
courses    = pd.read_csv("data/courses.csv")
rooms      = pd.read_csv("data/rooms.csv")
faculty_df = pd.read_csv("data/faculty.csv")

# Faculty availability map
faculty_availability = {}
for _, row in faculty_df.iterrows():
    faculty_availability[row["name"]] = row["available_slots"].split(",")

# Convert to lists
course_list = courses.to_dict(orient="records")
room_list   = rooms.to_dict(orient="records")

# All time slots (Mon–Fri, 8 periods)
time_slots = [
    f"{day}{p}"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for p in range(1, 9)
]

# -------------------- FITNESS FUNCTION --------------------
def fitness(timetable):
    """
    Returns a score starting at 1000.
    Penalties:
      -50  per faculty clash (same faculty, same slot)
      -40  per room clash   (same room, same slot)
      -30  per elective clash (two electives in same slot)
      -20  per faculty outside their availability
    Higher score = better timetable. Perfect = 1000.
    """
    score = 1000
    n = len(timetable)

    # Count clashes between each pair
    for i in range(n):
        for j in range(i + 1, n):
            if timetable[i]["slot"] == timetable[j]["slot"]:
                if timetable[i]["faculty"] == timetable[j]["faculty"]:
                    score -= 50
                if timetable[i]["room"] == timetable[j]["room"]:
                    score -= 40
                if timetable[i]["type"] == "elective" and timetable[j]["type"] == "elective":
                    score -= 30

    # Faculty availability
    for entry in timetable:
        faculty = entry["faculty"]
        slot    = entry["slot"]
        allowed = faculty_availability.get(faculty, time_slots)
        if slot not in allowed:
            score -= 20

    return score

MAX_SCORE = 1000  # Perfect score (no conflicts at all)

# -------------------- RANDOM TIMETABLE --------------------
def generate_random_timetable():
    timetable = []
    for course in course_list:
        faculty = course["faculty"]
        valid_slots = faculty_availability.get(faculty, time_slots)
        slot = random.choice(valid_slots)
        room = random.choice(room_list)
        timetable.append({
            "course":  course["course_name"],
            "faculty": faculty,
            "slot":    slot,
            "room":    room["room_name"],
            "type":    course["type"]
        })
    return timetable

# -------------------- TOURNAMENT SELECTION --------------------
def tournament_selection(population, k=5):
    """Pick k random individuals and return the best."""
    contestants = random.sample(population, min(k, len(population)))
    return max(contestants, key=fitness)

# -------------------- CROSSOVER --------------------
def crossover(parent1, parent2):
    """Single-point crossover."""
    point = random.randint(1, len(parent1) - 1)
    child = parent1[:point] + parent2[point:]
    return [entry.copy() for entry in child]

# -------------------- SMART MUTATION --------------------
def mutate(timetable, mutation_rate=0.3):
    """
    With probability mutation_rate, mutate each gene.
    Mutation respects faculty availability — picks from valid slots only.
    Also randomises room.
    """
    for entry in timetable:
        if random.random() < mutation_rate:
            faculty     = entry["faculty"]
            valid_slots = faculty_availability.get(faculty, time_slots)
            entry["slot"] = random.choice(valid_slots)
            entry["room"] = random.choice(room_list)["room_name"]
    return timetable

# -------------------- INITIAL POPULATION --------------------
POP_SIZE   = 100
GENERATIONS = 300
ELITE_COUNT = 5   # Top N survivors carried unchanged each generation

population = [generate_random_timetable() for _ in range(POP_SIZE)]

print("=" * 60)
print("  AI Timetable System - Genetic Algorithm")
print("=" * 60)
print(f"  Courses   : {len(course_list)}")
print(f"  Rooms     : {len(room_list)}")
print(f"  Faculties : {len(faculty_availability)}")
print(f"  Time Slots: {len(time_slots)}")
print(f"  Population: {POP_SIZE}  |  Generations: {GENERATIONS}")
print("=" * 60)

# -------------------- GENETIC ALGORITHM --------------------
for gen in range(GENERATIONS):
    # Evaluate and sort
    population.sort(key=fitness, reverse=True)
    best_score = fitness(population[0])

    # Print every 25 generations + first + last
    if gen == 0 or (gen + 1) % 25 == 0 or best_score == MAX_SCORE:
        print(f"  Gen {gen+1:>3} | Best Score: {best_score}/{MAX_SCORE}")

    # Early stop if perfect solution found
    if best_score == MAX_SCORE:
        print(f"\n  [OK] Perfect solution found at generation {gen+1}!")
        break

    # Elitism — carry top individuals unchanged
    new_population = [ind.copy() for ind in population[:ELITE_COUNT]]
    # Deep copy elite entries
    new_population = [[e.copy() for e in ind] for ind in population[:ELITE_COUNT]]

    # Fill rest via tournament selection → crossover → mutation
    while len(new_population) < POP_SIZE:
        p1 = tournament_selection(population)
        p2 = tournament_selection(population)
        child = crossover(p1, p2)
        # Adaptive mutation: higher rate early on, lower later
        rate = max(0.05, 0.4 - (gen / GENERATIONS) * 0.35)
        child = mutate(child, mutation_rate=rate)
        new_population.append(child)

    population = new_population

# -------------------- BEST RESULT --------------------
best_timetable = max(population, key=fitness)
best_score     = fitness(best_timetable)

print("\n" + "=" * 60)
print(f"  Final Best Score: {best_score}/{MAX_SCORE}")
print("=" * 60)

# -------------------- CLASH DIAGNOSTICS --------------------
clashes = []
n = len(best_timetable)
for i in range(n):
    for j in range(i + 1, n):
        if best_timetable[i]["slot"] == best_timetable[j]["slot"]:
            if best_timetable[i]["faculty"] == best_timetable[j]["faculty"]:
                clashes.append(
                    f"  [!!] FACULTY CLASH: {best_timetable[i]['faculty']} "
                    f"teaching '{best_timetable[i]['course']}' AND "
                    f"'{best_timetable[j]['course']}' at slot {best_timetable[i]['slot']}"
                )
            if best_timetable[i]["room"] == best_timetable[j]["room"]:
                clashes.append(
                    f"  [!!] ROOM CLASH: {best_timetable[i]['room']} used by "
                    f"'{best_timetable[i]['course']}' AND "
                    f"'{best_timetable[j]['course']}' at slot {best_timetable[i]['slot']}"
                )

if clashes:
    print("\n  Remaining Conflicts:")
    for c in clashes:
        print(c)
else:
    print("\n  [OK] No conflicts - perfect timetable generated!")

# Availability check
print("\n  Faculty Availability Violations:")
violations = False
for entry in best_timetable:
    allowed = faculty_availability.get(entry["faculty"], time_slots)
    if entry["slot"] not in allowed:
        print(f"  [!!] {entry['faculty']} scheduled at {entry['slot']} "
              f"(not in their availability) for '{entry['course']}'")
        violations = True
if not violations:
    print("  [OK] All faculty scheduled within their available slots!")

# -------------------- DETAILED TIMETABLE --------------------
print("\n" + "=" * 60)
print("  Final Optimized Timetable")
print("=" * 60)

best_sorted = sorted(best_timetable, key=lambda x: (x["slot"][:3], int(x["slot"][3:])))
for t in best_sorted:
    day    = t["slot"][:3]
    period = t["slot"][3:]
    print(f"  {day} Period {period}  ->  {t['course']:<35} | {t['faculty']:<15} | {t['room']}")

# -------------------- GRID VIEW --------------------
days    = ["Mon", "Tue", "Wed", "Thu", "Fri"]
periods = [str(i) for i in range(1, 9)]

grid = {day: {p: "Free" for p in periods} for day in days}

for t in best_timetable:
    day    = t["slot"][:3]
    period = t["slot"][3:]
    if day in grid and period in grid[day]:
        grid[day][period] = f"{t['course']} ({t['room']})"

grid_df = pd.DataFrame(grid).T
grid_df.index.name = "Day \\ Period"

print("\n" + "=" * 60)
print("  Timetable Grid")
print("=" * 60)
print(grid_df.to_string())