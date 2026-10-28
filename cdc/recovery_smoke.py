"""Real Docker CDC recovery checks, restricted to the isolated demo project.

Start first:
docker compose -p codex-cdc-recovery --env-file cdc/.env.recovery -f docker-compose.cdc.yml up -d --build cdc-consumer persona-worker

No embedding-provider API calls: provider failure is injected in a one-off process.
"""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "codex-cdc-recovery"
BASE = ["docker", "compose", "-p", PROJECT, "--env-file", str(ROOT / "cdc/.env.recovery"),
        "-f", str(ROOT / "docker-compose.cdc.yml")]


def command(*args, expected=0):
    result = subprocess.run([*BASE, *args], capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode != expected:
        raise RuntimeError(f"Docker command failed ({result.returncode}): {result.stderr[-1500:]}")
    return result.stdout.strip()


def mongo(expression):
    output = command("exec", "-T", "cdc-mongo", "mongosh", "financial_products", "--quiet", "--eval",
                     f"print(JSON.stringify({expression}))")
    return json.loads(output)


def user():
    return mongo("db.user_vectors.findOne({user_id:1})")


def sql(query):
    command("exec", "-T", "cdc-mysql", "mysql", "--default-character-set=utf8mb4", "-uapp", "-papp_demo", "knowhow", "-e", query)


def once(code, expected=0):
    return command("run", "--rm", "--no-deps", "persona-worker", "python", "-c", code, expected=expected)


def until(predicate, timeout=90):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            if predicate():
                return round(time.monotonic() - started, 3)
        except RuntimeError:
            pass  # A container/database can still be starting after an explicit restart.
        time.sleep(1)
    raise AssertionError("Recovery condition timed out")


def balance(value):
    return value in (user() or {}).get("persona_text", "")


def main():
    cid = command("ps", "-q", "cdc-mysql")
    if not cid:
        raise RuntimeError("Start isolated recovery containers first")
    inspect = subprocess.run(["docker", "inspect", cid], capture_output=True, encoding="utf-8", check=True)
    labels = json.loads(inspect.stdout)[0]["Config"]["Labels"]
    if labels.get("com.docker.compose.project") != PROJECT:
        raise RuntimeError("Refusing to modify a non-demo Docker project")
    # Fixture guard: all code below only runs in this separately named Docker project.
    once("from app.pipelines.worker import restart_connector; restart_connector()")
    sql("UPDATE users SET investment_tendancy='안정추구형' WHERE user_id=1; UPDATE keyword SET name='안정적 생활비' WHERE keyword_id=1; UPDATE assets SET balance=100000000.00 WHERE asset_id=1; UPDATE user_info SET retirement_status=0 WHERE user_id=1;")
    until(lambda: bool((user() or {}).get("persona_text")))
    until(lambda: balance("100000000.00"))
    results = {}

    command("stop", "cdc-consumer")
    sql("UPDATE assets SET balance=314159.26 WHERE asset_id=1; UPDATE user_info SET retirement_status=1 WHERE user_id=1;")
    time.sleep(2)
    assert not balance("314159.26"), "CDC stopped but an unexpected writer refreshed the persona"
    command("start", "cdc-consumer")
    results["consumer_restart_replay_seconds"] = until(lambda: balance("314159.26"))
    print("PASS consumer stop/change/restart", flush=True)

    command("stop", "persona-worker")
    sql("UPDATE assets SET balance=271828.18 WHERE asset_id=1;")
    until(lambda: mongo("db.user_refresh_jobs.findOne({_id:1})") is not None)
    once("from app.pipelines.worker import queue; import os; j=queue().next_job(); assert j is not None; os._exit(137)", expected=137)
    assert mongo("db.user_refresh_jobs.findOne({_id:1})").get("lease_token")
    command("start", "persona-worker")
    results["abandoned_lease_recovery_seconds"] = until(lambda: balance("271828.18"))
    print("PASS abrupt exit after claim / lease recovery", flush=True)

    once("from confluent_kafka import Producer; p=Producer({'bootstrap.servers':'kafka:9092'}); p.produce('knowhow.knowhow.assets', value=b'raw_finance_secret{', partition=0); assert p.flush(10)==0")
    until(lambda: mongo("db.cdc_dead_letters.countDocuments({status:'failed'})") > 0)
    assert "raw_finance_secret" not in json.dumps(mongo("db.cdc_dead_letters.find().toArray()"))
    sql("UPDATE assets SET balance=161803.39 WHERE asset_id=1;")
    results["healthy_event_after_poison_seconds"] = until(lambda: balance("161803.39"))
    print("PASS poison quarantine / following event processing", flush=True)

    command("stop", "cdc-mysql")
    once("""
from app.services.user_vectorization_service import user_vectorization_service as s
from sqlalchemy.exc import SQLAlchemyError
try:
    s.get_current_persona(1)
except SQLAlchemyError:
    print('SOURCE_FAILURE_BLOCKED')
else:
    raise AssertionError('Unexpected stale-context fallback')
""")
    command("start", "cdc-mysql")
    until(lambda: command("exec", "-T", "cdc-mysql", "mysqladmin", "ping", "-h", "localhost", "-proot_demo") != "")
    once("from app.pipelines.worker import restart_connector; restart_connector()")
    sql("UPDATE assets SET balance=141421.35 WHERE asset_id=1;")
    results["mysql_connector_recovery_seconds"] = until(lambda: balance("141421.35"))
    print("PASS source outage / stale-context prevention / connector recovery", flush=True)

    once("""
from app.services.user_vectorization_service import user_vectorization_service as s
p = s.projection
p.max_attempts = 2
p.refresh(1)
def unavailable(_):
    raise ConnectionError('injected provider outage')
p.embedder = unavailable
for _ in range(2):
    p.collection.update_many({}, {'$unset': {'embedding_retry_at': ''}})
    try:
        p.embed_pending(1)
    except ConnectionError:
        pass
    else:
        raise AssertionError('Expected provider failure')
assert p.collection.find_one({'user_id':1})['embedding_status'] == 'failed'
assert '141421.35' in s.get_current_persona(1)
assert p.collection.find_one({'user_id':1})['embedding_status'] == 'failed'
assert p.retry_embedding(1)
p.embedder = lambda _: [0.1, 0.2]
assert p.embed_pending(1)
assert p.current_embedding(1) == [0.1, 0.2]
""")
    print("PASS injected provider outage / persona availability / manual retry", flush=True)
    report = {"project": PROJECT, "passed_scenarios": 5, "recovery_timings": results,
              "external_embedding_api_called": False}
    (ROOT / "cdc/recovery-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
