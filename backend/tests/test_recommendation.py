import unittest
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app
from backend.app.models import Base, CardDocument

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
        self.assertEqual(a, b)
        self.assertEqual(a, sorted(a, key=lambda x: (-x['score'], -x['estimated_net_annual_value'], x['id'])))

    def test_score_explanation_and_confidence_are_measurable(self):
        result = self.client.post('/api/recommend', json=self.profile).json()
        first = result['recommendations'][0]
        self.assertEqual(set(first['score_breakdown']), {'spending_match','reward_value','preference_match','eligibility','fee_value','benefits'})
        self.assertTrue(0 <= first['score'] <= 100)
        self.assertTrue(0 <= first['confidence'] <= 100)
        self.assertTrue(first['confidence_reason'])
        self.assertTrue(first['why'])
        self.assertTrue(first['why_not'])
        self.assertIn('shopping', first['category_rewards'])

    def test_missing_eligibility_values_lower_completeness(self):
        result = self.client.post('/api/recommend', json={"spending":{"shopping":1000}}).json()
        self.assertTrue(result['recommendations'])
        self.assertTrue(all(x['profile_completeness'] < 100 for x in result['recommendations']))
        self.assertIn('unknown', result['recommendations'][0]['confidence_reason'])

    def test_negative_spending_is_rejected(self):
        response = self.client.post('/api/recommend', json={"spending":{"fuel":-1}})
        self.assertEqual(response.status_code, 422)

    def test_simulation_accepts_multiple_inputs_and_returns_rank_movements(self):
        result = self.client.post('/api/simulate', json={"profile":self.profile,"changes":{"travel":15000,"shopping":12000,"annual_fee_max":2000}})
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertNotEqual(body['before']['recommendations'][0]['estimated_net_annual_value'], body['after']['recommendations'][0]['estimated_net_annual_value'])
        self.assertIn('explanation', body)
        self.assertIn('moved', body)

    def test_simulation_rejects_unknown_fields(self):
        result = self.client.post('/api/simulate', json={"profile":self.profile,"changes":{"rent":2000}})
        self.assertEqual(result.status_code, 422)

    def test_personalized_comparison(self):
        ranked = self.client.post('/api/recommend', json=self.profile).json()['recommendations']
        result = self.client.post('/api/compare', json={"profile":self.profile,"card_ids":[ranked[0]['id'],ranked[1]['id']]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()['cards']), 2)

    def test_empty_rag_returns_insufficient_evidence(self):
        with patch('backend.app.main.configured_embedding_provider', return_value=None):
            response = self.client.post('/api/rag/search', json={"query":"lounge access"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['grounded'])
        self.assertIn('not have enough verified information', response.json()['answer'])

    def test_factual_chat_uses_rag_and_never_guesses(self):
        with patch('backend.app.main.configured_embedding_provider', return_value=None):
            response = self.client.post('/api/chat', json={"message":"Does this card have lounge access?","profile":self.profile})
        self.assertFalse(response.json()['grounded'])
        self.assertEqual(response.json()['tools_called'], ['search_card_knowledge'])

    def test_voice_unavailable_is_a_controlled_fallback(self):
        with patch('backend.app.main.configured_voice_provider', return_value=None):
            transcribe = self.client.post('/api/voice/transcribe', files={"audio":("clip.webm",b"audio","audio/webm")}, data={"language":"en"})
            speak = self.client.post('/api/voice/speak', json={"text":"Hello","language":"en"})
        self.assertEqual(transcribe.status_code, 503)
        self.assertEqual(speak.status_code, 503)
        self.assertIn('Continue with text', transcribe.json()['detail']['message'])

    def test_models_include_required_relational_tables_and_vector(self):
        required = {'users','user_profiles','credit_cards','card_benefits','card_documents','recommendations','recommendation_explanations','conversation_sessions','conversation_messages','simulation_history'}
        self.assertTrue(required.issubset(set(Base.metadata.tables)))
        self.assertIn('embedding', CardDocument.__table__.columns)

if __name__ == '__main__':
    unittest.main()
