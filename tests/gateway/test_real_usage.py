import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pymongo import MongoClient

from app.gateway.usage import MongoUsage

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MONGO_URL'), reason='Set isolated TEST_MONGO_URL')


def test_real_ledger_idempotency_cost_unknown_usage_and_filters():
    async def case():
        client = MongoClient(os.environ['TEST_MONGO_URL'],serverSelectionTimeoutMS=3000)
        db_name = 'gateway_test_' + uuid4().hex
        collection = client[db_name]['usage']
        usage = MongoUsage(collection,input_price=1,output_price=2)
        try:
            await usage.initialize()
            base = {'attempt_id':'a','user_id':'7','feature':'chat','provider':'groq','model':'m',
                    'timestamp':datetime.now(timezone.utc),'status':'started','outbound_started':False,
                    'input_tokens':None,'output_tokens':None,'total_tokens':None}
            await usage.record(base)
            success = {**base,'status':'success','outbound_started':True,
                       'input_tokens':100,'output_tokens':50,'total_tokens':150}
            await usage.record(success)
            await usage.record(success)  # Same attempt must not double bill.
            await usage.record(base)  # Delayed started write cannot erase finalized usage.
            await usage.record({**base,'attempt_id':'b','status':'provider_429','outbound_started':True})
            await usage.record({**base,'attempt_id':'c','status':'rejected','feature':'recommendations'})
            await usage.record({**base,'attempt_id':'d','user_id':'8'})
            result = await usage.summary(7,7)
            assert len(result['rows']) == 2
            row = next(r for r in result['rows'] if r['_id']['feature'] == 'chat')
            assert row['outbound_attempts'] == 2 and row['successful_calls'] == 1
            assert row['provider_429'] == 1 and row['unknown_usage_calls'] == 1
            assert row['input_tokens'] == 100 and row['output_tokens'] == 50
            assert row['estimated_cost_usd'] == pytest.approx(.0002)
            assert row['priced_calls'] == 1
            assert collection.count_documents({}) == 4
            indexes = collection.index_information()
            assert indexes['attempt_id_1']['unique']
            assert indexes['expires_at_1']['expireAfterSeconds'] == 0
        finally:
            # Only the unique database created by THIS test is removed.
            client.drop_database(db_name)
            client.close()
    asyncio.run(case())
