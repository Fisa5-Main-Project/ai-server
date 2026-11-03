"""Attempt ledger; chat message counts are not provider usage."""
import asyncio
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError


class MongoUsage:
    def __init__(self, collection, retention_days=90, input_price=None, output_price=None):
        self.collection, self.retention_days = collection, retention_days
        self.input_price, self.output_price = input_price, output_price

    async def initialize(self):
        def indexes():
            self.collection.create_index('attempt_id', unique=True)
            self.collection.create_index([('timestamp', -1), ('user_id', 1)])
            self.collection.create_index('expires_at', expireAfterSeconds=0)
        await asyncio.to_thread(indexes)

    async def record(self, event):
        doc = dict(event)
        doc['state_version'] = 0 if doc['status'] == 'started' else 1
        doc['expires_at'] = doc['timestamp'] + timedelta(days=self.retention_days)
        known = doc.get('input_tokens') is not None and doc.get('output_tokens') is not None
        doc['usage_known'] = known
        doc['estimated_cost_usd'] = None
        if known and self.input_price is not None and self.output_price is not None:
            doc['estimated_cost_usd'] = (doc['input_tokens'] * self.input_price +
                                         doc['output_tokens'] * self.output_price) / 1_000_000
            doc['price_snapshot'] = {'input_per_million':self.input_price,'output_per_million':self.output_price}
        def update():
            # A timed-out thread may finish late: an old start must not overwrite a terminal record.
            try:
                self.collection.update_one({'attempt_id':doc['attempt_id'], '$or':[
                    {'state_version':{'$lte':doc['state_version']}}, {'state_version':{'$exists':False}}]},
                    {'$set':doc}, upsert=True)
            except DuplicateKeyError:
                existing = self.collection.find_one({'attempt_id':doc['attempt_id']},{'state_version':1})
                if not existing or existing.get('state_version',0) <= doc['state_version']:
                    raise
        await asyncio.to_thread(update)

    async def summary(self, days=7, user_id=None):
        start = datetime.now(timezone.utc) - timedelta(days=days)
        match = {'timestamp':{'$gte':start}}
        if user_id is not None:
            match['user_id'] = str(user_id)
        def count_if(expression):
            return {'$sum':{'$cond':[expression,1,0]}}
        pipeline = [{'$match':match}, {'$group':{
            '_id':{'user_id':'$user_id','feature':'$feature','provider':'$provider','model':'$model'},
            'attempts':{'$sum':1},
            'outbound_attempts':count_if({'$eq':['$outbound_started',True]}),
            'successful_calls':count_if({'$eq':['$status','success']}),
            'provider_429':count_if({'$eq':['$status','provider_429']}),
            'rejected':count_if({'$eq':['$status','rejected']}),
            'failed':count_if({'$in':['$status',['failed','timeout','cancelled']]}),
            'unfinished':count_if({'$eq':['$status','started']}),
            'unknown_usage_calls':count_if({'$and':[{'$eq':['$outbound_started',True]},
                                                       {'$ne':['$usage_known',True]}]}),
            'input_tokens':{'$sum':'$input_tokens'}, 'output_tokens':{'$sum':'$output_tokens'},
            'total_tokens':{'$sum':'$total_tokens'}, 'estimated_cost_usd':{'$sum':'$estimated_cost_usd'},
            'priced_calls':count_if({'$ne':['$estimated_cost_usd',None]}),
        }}, {'$sort':{'outbound_attempts':-1,'_id.user_id':1,'_id.feature':1}}, {'$limit':501}]
        rows = await asyncio.to_thread(lambda:list(self.collection.aggregate(pipeline, maxTimeMS=5000)))
        return {'days':days, 'since':start.isoformat(), 'rows':rows[:500], 'truncated':len(rows)>500,
                'note':'미확인 토큰은 합계에서 제외됩니다. 비용은 설정 단가 기준 추정이며 청구액이 아닙니다.'}
