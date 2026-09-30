import unittest
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app
from backend.app.models import Base, CardDocument
from backend.app.database import get_session_factory
from datetime import date
import asyncio
import os
import uuid

class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.profile = {"monthly_income":70000,"credit_score":760,"annual_fee_max":1500,"reward_preference":"cashback","spending":{"shopping":15000,"dining":8000,"fuel":4000,"travel":5000}}

    def test_signup_login_logout_and_persisted_profile(self):
        email = f"cardlens-{uuid.uuid4()}@example.test"
        signup = self.client.post('/api/auth/signup', json={"email":email,"password":"correct horse 2026","name":"Test User"})
        self.assertEqual(signup.status_code, 201)
        self.assertTrue(signup.cookies.get("cardlens_session"))
        self.assertEqual(self.client.get('/api/auth/me').json()['user']['email'], email)
        self.assertNotIn("password_hash", signup.json()["user"])
        saved = self.client.put('/api/profile', json=self.profile)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["saved"])
        self.assertEqual(self.client.get('/api/profile').json()["profile"]["credit_score"], 760)
        ranked = self.client.post('/api/recommend', json=self.profile)
        self.assertEqual(ranked.status_code, 200)
        simulation = self.client.post('/api/simulate', json={"profile":self.profile,"changes":{"dining":9000}})
        self.assertEqual(simulation.status_code, 200)
        activity = self.client.get('/api/history').json()["items"]
        self.assertEqual({item["type"] for item in activity}, {"recommendation","simulation"})
        conversation = self.client.post('/api/conversations', json={"language":"en","messages":[{"role":"user","text":"Why this match?"},{"role":"assistant","text":"Because the profile fits."}]})
        self.assertEqual(conversation.status_code, 201)
        conversation_id = conversation.json()["conversation"]["id"]
        self.assertEqual(len(self.client.get('/api/conversations/latest').json()["conversation"]["messages"]), 2)
        favorite = self.client.post('/api/favorites/demo-travel')
        self.assertEqual(favorite.status_code, 201)
        self.assertEqual(self.client.get('/api/favorites').json()["items"][0]["card_id"], "demo-travel")
        self.assertEqual(self.client.delete('/api/favorites/demo-travel').status_code, 200)
        self.assertEqual(self.client.get('/api/favorites').json()["items"], [])
        other = TestClient(app)
        self.assertEqual(other.put(f'/api/conversations/{conversation_id}', json={"messages":[]}).status_code, 401)
        duplicate = self.client.post('/api/auth/signup', json={"email":email,"password":"correct horse 2026","name":"Test User"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/profile').status_code, 401)
        login = self.client.post('/api/auth/login', json={"email":email,"password":"correct horse 2026"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get('/api/profile').json()["profile"]["credit_score"], 760)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)

    def test_profile_requires_authentication(self):
        response = self.client.get('/api/profile')
        self.assertEqual(response.status_code, 401)
        response = self.client.put('/api/profile', json=self.profile)
        self.assertEqual(response.status_code, 401)

    def test_profile_validation_and_card_detail_routes(self):
        card = self.client.get('/api/cards/demo-travel')
        self.assertEqual(card.status_code, 200)
        self.assertIn('Synthetic demo data', card.json()['notice'])
        self.assertEqual(self.client.get('/api/cards/not-real').status_code, 404)

    def test_natural_language_profile_extraction_returns_reviewable_values(self):
        text = "I earn around ₹70,000 a month. I spend ₹15,000 online, ₹8,000 on dining, ₹4,000 on fuel and ₹5,000 on travel. My credit score is 760 and I prefer cashback."
        response = self.client.post('/api/profile/extract', json={"text":text})
        self.assertEqual(response.status_code, 200)
        extracted = response.json()['extracted_fields']
        self.assertEqual(extracted['monthly_income'], 70000)
        self.assertEqual(extracted['credit_score'], 760)
        self.assertEqual(extracted['reward_preference'], 'cashback')
        self.assertEqual(extracted['spending']['shopping'], 15000)
        self.assertTrue(response.json()['requires_confirmation'])

    def test_invalid_llm_extraction_retries_then_uses_explicit_local_values(self):
        class BadProvider:
            calls = 0
            async def chat(self, messages, tools=None):
                self.calls += 1
                return {"content":"not json"}
        provider = BadProvider()
        with patch('backend.app.main.configured_provider', return_value=provider):
            response = self.client.post('/api/profile/extract', json={"text":"My monthly income is ₹40,000 and I spend ₹3,000 on fuel."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['method'], 'deterministic')
        self.assertEqual(provider.calls, 2)
        self.assertEqual(response.json()['extracted_fields']['spending']['fuel'], 3000)

    def test_health_and_demo_catalog_notice(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/ready').status_code, 200)
        self.assertIn('Synthetic demo data', self.client.get('/api/cards').json()['notice'])

    def test_production_requires_explicit_database_and_https_origins(self):
        from backend.app.main import validate_runtime_configuration
        with patch.dict(os.environ, {"APP_ENV":"production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL, FRONTEND_ORIGINS"):
                validate_runtime_configuration()
        with patch.dict(os.environ, {"APP_ENV":"production","DATABASE_URL":"postgresql://db/cardlens","FRONTEND_ORIGINS":"*"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HTTPS origins"):
                validate_runtime_configuration()

    def test_readiness_returns_controlled_database_error(self):
        with patch('backend.app.main.check_database', return_value=(False, 'database_unavailable')):
            response = self.client.get('/ready')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail']['error_code'], 'DATABASE_UNAVAILABLE')
        self.assertNotIn('Traceback', response.text)

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
        self.assertIn('enough verified information', response.json()['answer'])

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

    def test_advisor_recalculates_when_asked_why_simulation_changed(self):
        last = self.client.post('/api/simulate', json={"profile":self.profile,"changes":{"travel":15000}}).json()
        response = self.client.post('/api/chat', json={"message":"Why did the ranking change?","profile":self.profile,"last_simulation":last})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tools_called'], ['run_what_if_simulation'])
        self.assertIn('simulation', response.json())

    def test_llm_tool_call_uses_backend_ranking_result(self):
        class FakeProvider:
            async def chat(self, messages, tools=None):
                if tools:
                    return {"tool_calls":[{"id":"test-call","function":{"name":"get_recommendations","arguments":"{}"}}]}
                self.assert_tool_result = any(m.get("role") == "tool" for m in messages)
                return {"content":"Based on the calculated CardLens result, here is the explanation."}
        fake = FakeProvider()
        with patch('backend.app.main.configured_provider', return_value=fake):
            response = self.client.post('/api/chat', json={"message":"Why did you recommend this card?","profile":self.profile})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'llm_tools')
        self.assertIn('get_recommendations', response.json()['tools_called'])
        self.assertTrue(fake.assert_tool_result)

    def test_pgvector_retrieval_returns_source_metadata(self):
        factory = get_session_factory()
        if factory is None:
            self.skipTest("PostgreSQL service is only configured in CI")
        doc = CardDocument(id="rag-test-document",card_id="demo-travel",card_name="Demo travel card",source="https://example.org/verified-terms",document_version="test-v1",last_verified=date(2026,9,30),chunk_text="This test source states that lounge entry has a stated visit condition.",embedding=[1.0]+[0.0]*383,is_demo=False)
        with factory.begin() as session:
            session.merge(doc)
        class FakeEmbedding:
            async def embed(self, text):
                return [1.0]+[0.0]*383
        async def run_search():
            from backend.app.rag import search_card_knowledge
            return await search_card_knowledge("lounge access",FakeEmbedding(),"demo-travel")
        try:
            from unittest.mock import patch
            with patch("backend.app.rag.get_session_factory",return_value=factory):
                result = asyncio.run(run_search())
            self.assertTrue(result['grounded'])
            self.assertEqual(result['sources'][0]['source'],"https://example.org/verified-terms")
        finally:
            with factory.begin() as session:
                session.query(CardDocument).filter(CardDocument.id == "rag-test-document").delete()

    def test_models_include_required_relational_tables_and_vector(self):
        required = {'users','user_profiles','credit_cards','card_benefits','card_documents','recommendations','recommendation_explanations','conversation_sessions','conversation_messages','simulation_history'}
        self.assertTrue(required.issubset(set(Base.metadata.tables)))
        self.assertIn('embedding', CardDocument.__table__.columns)

if __name__ == '__main__':
    unittest.main()
