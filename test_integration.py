import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'frontend'))

import unittest
import json
from app import app

class TestChronoGenApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['TESTING'] = True

    def test_1_login_page_loads(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Login", response.data)

    def test_2_failed_login(self):
        response = self.client.post('/login', data={
            "email": "test@example.com",
            "password": "wrongpassword"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid email or password", response.data)

    def test_3_successful_login_and_dashboard(self):
        # login
        response = self.client.post('/login', data={
            "email": "test@example.com",
            "password": "password123"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ChronoGen", response.data)
        self.assertIn(b"Signed in as", response.data)

        # Test analytics endpoint (authorized session because client retains session/cookies)
        response_analytics = self.client.get('/analytics')
        self.assertEqual(response_analytics.status_code, 200)
        data = json.loads(response_analytics.data)
        self.assertIn("total_teaching_slots", data)
        self.assertIn("faculty_workload", data)

    def test_4_validate_endpoint(self):
        # Scenario 1: Slot occupied, normal swap
        payload = {
            "target_slot": "Mon1",
            "faculty": "Dr. Smith",
            "room": "Room 101",
            "grid": {
                "Mon": {
                    "1": {"faculty": "Dr. Jones", "room": "Room 102", "course": "Physics"}
                }
            }
        }
        response = self.client.post('/validate', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "soft")

        # Scenario 2: Faculty conflict
        payload_conflict = {
            "target_slot": "Mon1",
            "faculty": "Dr. Jones",
            "room": "Room 101",
            "grid": {
                "Mon": {
                    "1": {"faculty": "Dr. Jones", "room": "Room 102", "course": "Physics"}
                }
            }
        }
        response2 = self.client.post('/validate',
                                     data=json.dumps(payload_conflict),
                                     content_type='application/json')
        self.assertEqual(response2.status_code, 200)
        data2 = json.loads(response2.data)
        self.assertEqual(data2["status"], "hard")
        self.assertIn("already has a class", data2["reason"])

if __name__ == "__main__":
    unittest.main()
