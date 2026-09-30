import unittest
from fastapi.testclient import TestClient
from backend.app.main import app

class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.profile = {"monthly_income":70000,"credit_score":760,"annual_fee_max":1500,"reward_preference":"cashback","spending":{"shopping":15000,"dining":8000,"fuel":4000,"travel":5000}}

    def test_health_and_demo_catalog_notice(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertIn('Synthetic demo data', self.client.get('/api/cards').json()['notice'])

    def test_recommendations_are_deterministic_and_ranked(self):
        a = self.client.post('/api/recommend', json=self.profile).json()['recommendations']
        b = self.client.post('/api/recommend', json=self.profile).json()['recommendations']
        self.assertEqual([x['id'] for x in a], [x['id'] for x in b])
        self.assertEqual(a, b)
        self.assertEqual(a, sorted(a, key=lambda x: (-x['score'], -x['estimated_net_annual_value'], x['id'])))

    def test_missing_eligibility_values_are_not_invented(self):
        result = self.client.post('/api/recommend', json={"spending":{"shopping":1000}}).json()
        self.assertTrue(result['recommendations'])
        self.assertTrue(all(x['profile_completeness'] < 100 for x in result['recommendations']))

    def test_negative_spending_is_rejected(self):
        response = self.client.post('/api/recommend', json={"spending":{"fuel":-1}})
        self.assertEqual(response.status_code, 422)

    def test_simulation_uses_updated_profile(self):
        result = self.client.post('/api/simulate', json={"profile":self.profile,"changes":{"travel":15000}})
        self.assertEqual(result.status_code, 200)
        self.assertNotEqual(result.json()['before']['recommendations'][0]['estimated_net_annual_value'], result.json()['after']['recommendations'][0]['estimated_net_annual_value'])

if __name__ == '__main__':
    unittest.main()
