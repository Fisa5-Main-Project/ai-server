"""Idempotently register Debezium. Secrets come from environment, never stdout."""
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import URLError


def configuration(env):
    database = env.get("CDC_DATABASE", "knowhow")
    prefix = env.get("CDC_TOPIC_PREFIX", "knowhow")
    columns = {"users": ["user_id"], "user_info": ["user_info_id", "user_id"],
               "assets": ["asset_id", "user_id"], "user_keyword": ["user_id", "keyword_id"],
               "keyword": ["keyword_id"]}
    return {
        "connector.class": "io.debezium.connector.mysql.MySqlConnector",
        "tasks.max": "1", "database.hostname": env["CDC_MYSQL_HOST"],
        "database.port": env.get("CDC_MYSQL_PORT", "3306"),
        "database.user": env["CDC_MYSQL_USER"], "database.password": env["CDC_MYSQL_PASSWORD"],
        "database.server.id": env.get("CDC_MYSQL_SERVER_ID", "184055"),
        "topic.prefix": prefix, "database.include.list": database,
        "table.include.list": ",".join(f"{database}.{table}" for table in columns),
        # Events only route invalidations. Do not put password/phone/assets in Kafka.
        "column.include.list": ",".join(f"{database}.{table}.{column}" for table, names in columns.items() for column in names),
        "snapshot.mode": "initial", "include.schema.changes": "false",
        "schema.history.internal.kafka.bootstrap.servers": env.get("CDC_KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "schema.history.internal.kafka.topic": f"{prefix}.schema-history",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false", "value.converter.schemas.enable": "false",
    }


def main():
    base = os.environ.get("CDC_CONNECT_URL", "http://connect:8083").rstrip("/")
    config = configuration(os.environ)
    for _ in range(60):
        try:
            request = Request(f"{base}/connectors/user-state-cdc/config", method="PUT",
                              data=json.dumps(config).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=10) as response:
                if response.status not in (200, 201):
                    raise RuntimeError("Connector registration failed")
            print("Connector configuration registered. Check /connectors/user-state-cdc/status for RUNNING.")
            return
        except URLError:
            time.sleep(2)
    raise RuntimeError("Connect unavailable or rejected configuration; inspect Connect logs")


if __name__ == "__main__":
    main()
