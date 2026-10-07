"""One committed, repeatable-read MySQL snapshot with a reusable engine."""
from sqlalchemy import text


class UserNotFound(ValueError):
    pass


class MySQLUserSource:
    def __init__(self, engine, projections=None):
        self.engine = engine
        self.projections = projections

    def read(self, user_id: int) -> dict:
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            with conn.begin():
                user = conn.execute(text("""
                    SELECT user_id, birth, gender, asset_total, investment_tendancy,
                           user_mydata_registration FROM users WHERE user_id = :id
                """), {"id": user_id}).mappings().first()
                if user is None:
                    raise UserNotFound(f"User {user_id} not found")
                info = conn.execute(text("SELECT * FROM user_info WHERE user_id = :id"),
                                    {"id": user_id}).mappings().first()
                keywords = conn.execute(text("""
                    SELECT k.keyword_id, k.name FROM keyword k JOIN user_keyword uk ON k.keyword_id = uk.keyword_id
                    WHERE uk.user_id = :id ORDER BY k.keyword_id
                """), {"id": user_id}).mappings().all()
                assets = conn.execute(text("SELECT type, balance FROM assets WHERE user_id = :id"),
                                      {"id": user_id}).mappings().all()
                return {"user": dict(user), "user_info": dict(info) if info else {},
                        "keywords": [dict(row) for row in keywords], "assets": [dict(row) for row in assets]}

    def users_for_keyword(self, keyword_id):
        with self.engine.connect() as conn:
            ids = {row[0] for row in conn.execute(
                text("SELECT user_id FROM user_keyword WHERE keyword_id = :id"), {"id": keyword_id})}
        # MySQL cascaded FK deletions need not emit child-table binlog events.
        # Retain the reverse links in the projection to route a keyword deletion.
        if self.projections is not None:
            ids.update(doc["user_id"] for doc in self.projections.find(
                {"keyword_ids": int(keyword_id), "deleted": False}, {"user_id": 1}))
        return ids

    def user_ids(self):
        with self.engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(text("SELECT user_id FROM users ORDER BY user_id")):
                yield row[0]
