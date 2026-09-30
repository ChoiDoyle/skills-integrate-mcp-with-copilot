"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

DEFAULT_ACTIVITIES = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}

DATABASE_PATH = Path(os.getenv("ACTIVITIES_DB_PATH", current_dir / "activities.sqlite"))


@contextmanager
def get_database_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,
                max_participants INTEGER NOT NULL CHECK (max_participants >= 0)
            );
            CREATE TABLE IF NOT EXISTS participants (
                activity_name TEXT NOT NULL REFERENCES activities(name) ON DELETE CASCADE,
                email TEXT NOT NULL,
                PRIMARY KEY (activity_name, email)
            );
            """
        )
        activity_count = connection.execute(
            "SELECT COUNT(*) FROM activities"
        ).fetchone()[0]
        if activity_count == 0:
            for name, details in DEFAULT_ACTIVITIES.items():
                connection.execute(
                    "INSERT INTO activities (name, description, schedule, max_participants) "
                    "VALUES (?, ?, ?, ?)",
                    (name, details["description"], details["schedule"], details["max_participants"]),
                )
                connection.executemany(
                    "INSERT INTO participants (activity_name, email) VALUES (?, ?)",
                    [(name, email) for email in details["participants"]],
                )


def get_activities_data() -> dict[str, dict[str, object]]:
    with get_database_connection() as connection:
        rows = connection.execute(
            "SELECT a.name, a.description, a.schedule, a.max_participants, p.email "
            "FROM activities AS a "
            "LEFT JOIN participants AS p ON p.activity_name = a.name "
            "ORDER BY a.rowid, p.rowid"
        ).fetchall()

    activities: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["name"] not in activities:
            activities[row["name"]] = {
                "description": row["description"],
                "schedule": row["schedule"],
                "max_participants": row["max_participants"],
                "participants": [],
            }
        if row["email"] is not None:
            activities[row["name"]]["participants"].append(row["email"])
    return activities


initialize_database()


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    return get_activities_data()


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity"""
    with get_database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        activity = connection.execute(
            "SELECT max_participants FROM activities WHERE name = ?",
            (activity_name,),
        ).fetchone()
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        participant_count = connection.execute(
            "SELECT COUNT(*) FROM participants WHERE activity_name = ?",
            (activity_name,),
        ).fetchone()[0]
        if connection.execute(
            "SELECT 1 FROM participants WHERE activity_name = ? AND email = ?",
            (activity_name, email),
        ).fetchone():
            raise HTTPException(status_code=400, detail="Student is already signed up")
        if participant_count >= activity["max_participants"]:
            raise HTTPException(status_code=400, detail="Activity is full")

        connection.execute(
            "INSERT INTO participants (activity_name, email) VALUES (?, ?)",
            (activity_name, email),
        )
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity"""
    with get_database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute(
            "SELECT 1 FROM activities WHERE name = ?", (activity_name,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Activity not found")

        result = connection.execute(
            "DELETE FROM participants WHERE activity_name = ? AND email = ?",
            (activity_name, email),
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=400,
                detail="Student is not signed up for this activity",
            )
    return {"message": f"Unregistered {email} from {activity_name}"}
