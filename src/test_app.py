import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi import HTTPException

import app


class ActivityPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "activities.sqlite"
        self.database_patch = patch.object(app, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        app.initialize_database()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_activities_and_signups_survive_database_reinitialization(self):
        app.signup_for_activity("Chess Club", "newstudent@mergington.edu")

        app.initialize_database()

        activities = app.get_activities()
        self.assertIn("Chess Club", activities)
        self.assertIn("newstudent@mergington.edu", activities["Chess Club"]["participants"])

    def test_duplicate_signup_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            app.signup_for_activity("Chess Club", "michael@mergington.edu")

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(error.exception.detail, "Student is already signed up")

    def test_concurrent_signups_cannot_exceed_activity_capacity(self):
        with app.get_database_connection() as connection:
            connection.execute(
                "UPDATE activities SET max_participants = 3 WHERE name = 'Chess Club'"
            )
        barrier = Barrier(2)

        def signup(email):
            barrier.wait()
            try:
                app.signup_for_activity("Chess Club", email)
                return "signed_up"
            except HTTPException as error:
                return error.detail

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(signup, [
                "student1@mergington.edu",
                "student2@mergington.edu",
            ]))

        self.assertEqual(results.count("signed_up"), 1)
        self.assertEqual(results.count("Activity is full"), 1)
        participants = app.get_activities()["Chess Club"]["participants"]
        self.assertEqual(len(participants), 3)


if __name__ == "__main__":
    unittest.main()