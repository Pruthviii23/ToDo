# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages
from datetime import date, timedelta
import uuid, os, json

app = Flask(__name__)
app.secret_key = "dev-secret-key"

# --------------------
# Config
# --------------------
XP_PER_LEVEL = 100
DATA_FILE = "data.json"

RANKS = [
    "Bronze I", "Bronze II",
    "Silver I", "Silver II",
    "Gold I", "Gold II",
    "Platinum I", "Platinum II",
    "Diamond I", "Diamond II",
    "Ace I", "Ace II",
    "GrandMaster I", "GrandMaster II"
]

BASE_XP = {"easy": 6, "medium": 8, "hard": 10}
MIN_XP = 2

# --------------------
# In-memory state
# --------------------
daily_tasks = []
one_time_tasks = []
xp = 0
level = 0
streak = 0
last_completed_date = None
last_reset_date = None

# --------------------
# Persistence helpers
# --------------------
def save_data():
    data = {
        "daily_tasks": daily_tasks,
        "one_time_tasks": one_time_tasks,
        "xp": xp,
        "level": level,
        "streak": streak,
        "last_completed_date": str(last_completed_date) if last_completed_date else None,
        "last_reset_date": str(last_reset_date) if last_reset_date else None
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def load_data():
    global daily_tasks, one_time_tasks, xp, level, streak, last_completed_date, last_reset_date
    if not os.path.exists(DATA_FILE):
        return
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    daily_tasks = data.get("daily_tasks", [])
    one_time_tasks = data.get("one_time_tasks", [])
    xp = data.get("xp", 0)
    level = data.get("level", 0)
    streak = data.get("streak", 0)
    last_completed_date = date.fromisoformat(data["last_completed_date"]) if data.get("last_completed_date") else None
    last_reset_date = date.fromisoformat(data["last_reset_date"]) if data.get("last_reset_date") else None

# --------------------
# Utilities
# --------------------
def generate_id(): return uuid.uuid4().hex

def get_xp_value(tier: str, level_index: int) -> int:
    factor = 0.8 ** level_index
    raw = BASE_XP.get(tier, BASE_XP["easy"]) * factor
    rounded = round(raw)
    return max(MIN_XP, rounded)

def get_rank(level_index: int) -> str:
    return RANKS[level_index] if 0 <= level_index < len(RANKS) else "MAX"

def give_xp(amount: int):
    global xp, level
    xp += amount
    leveled = False
    while xp >= XP_PER_LEVEL:
        xp -= XP_PER_LEVEL
        level += 1
        leveled = True
    save_data()
    return leveled

def reset_daily_if_new_day():
    global last_reset_date
    today = date.today()
    if last_reset_date is None or last_reset_date < today:
        for t in daily_tasks:
            t["done"] = False
        last_reset_date = today
        save_data()

def find_task_by_id(collection: list, task_id: str):
    tid = str(task_id)
    for item in collection:
        if str(item.get("id")) == tid:
            return item
    return None

# --------------------
# Routes
# --------------------
@app.route("/", methods=["GET", "POST"])
def index():
    reset_daily_if_new_day()

    if request.method == "POST":
        kind = request.form.get("kind", "daily")
        text = request.form.get("task", "").strip()
        tier = request.form.get("tier", "easy")
        if not text:
            flash("Please write a task before adding.")
            return redirect(url_for("index"))

        uid = generate_id()
        if kind == "one_time":
            one_time_tasks.append({
                "id": uid,
                "text": text,
                "tier": tier,
                "created_date": str(date.today())
            })
            flash("One-time task added.")
        else:
            daily_tasks.append({
                "id": uid,
                "text": text,
                "tier": tier,
                "last_completed_date": None,
                "done": False
            })
            flash("Daily task added.")
        save_data()
        return redirect(url_for("index"))

    progress_percent = int((xp / XP_PER_LEVEL) * 100) if XP_PER_LEVEL else 0
    xp_easy = get_xp_value("easy", level)
    xp_medium = get_xp_value("medium", level)
    xp_hard = get_xp_value("hard", level)

    return render_template("index.html",
        daily_tasks=daily_tasks,
        one_time_tasks=one_time_tasks,
        xp=xp, xp_per_level=XP_PER_LEVEL,
        level=level, rank=get_rank(level),
        progress_percent=progress_percent,
        streak=streak,
        xp_easy=xp_easy, xp_medium=xp_medium, xp_hard=xp_hard,
        messages=get_flashed_messages()
    )

@app.route("/complete/daily", methods=["POST"])
def complete_daily():
    global last_completed_date, streak
    reset_daily_if_new_day()

    task_id = request.form.get("task_id")
    task = find_task_by_id(daily_tasks, task_id)
    if task is None:
        flash("Task not found.")
        return redirect(url_for("index"))

    today = date.today()
    if task.get("last_completed_date") == str(today):
        task["done"] = True
        flash("Already completed today.")
        save_data()
        return redirect(url_for("index"))

    gained = get_xp_value(task["tier"], level)
    leveled = give_xp(gained)

    task["last_completed_date"] = str(today)
    task["done"] = True

    # streak
    if last_completed_date is None:
        streak = 1
    else:
        if last_completed_date == today:
            pass
        elif today - last_completed_date == timedelta(days=1):
            streak += 1
        else:
            streak = 1
    last_completed_date = today

    save_data()
    flash(f"+{gained} XP!")
    if leveled:
        flash("Level up! 🎉")
    return redirect(url_for("index"))

@app.route("/complete/one_time", methods=["POST"])
def complete_one_time():
    global last_completed_date, streak

    task_id = request.form.get("task_id")
    task = find_task_by_id(one_time_tasks, task_id)
    if task is None:
        flash("Task not found.")
        return redirect(url_for("index"))

    gained = get_xp_value("medium", level)
    leveled = give_xp(gained)

    one_time_tasks[:] = [t for t in one_time_tasks if str(t.get("id")) != str(task_id)]

    today = date.today()
    if last_completed_date is None:
        streak = 1
    else:
        if last_completed_date == today:
            pass
        elif today - last_completed_date == timedelta(days=1):
            streak += 1
        else:
            streak = 1
    last_completed_date = today

    save_data()
    flash(f"+{gained} XP! (one-time task)")
    if leveled:
        flash("Level up! 🎉")
    return redirect(url_for("index"))

@app.route("/reset")
def reset_all():
    global daily_tasks, one_time_tasks, xp, level, streak, last_completed_date, last_reset_date
    daily_tasks = []
    one_time_tasks = []
    xp = 0
    level = 0
    streak = 0
    last_completed_date = None
    last_reset_date = None
    save_data()
    flash("All data reset (in-memory).")
    return redirect(url_for("index"))

# --------------------
if __name__ == "__main__":
    load_data()
    app.run(debug=True)
