import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_connector_preserves_before_after_and_limits_sensitive_payload():
    spec = importlib.util.spec_from_file_location("register_connector", ROOT / "cdc/register_connector.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.configuration({"CDC_MYSQL_HOST": "mysql", "CDC_MYSQL_USER": "cdc", "CDC_MYSQL_PASSWORD": "test"})
    assert config["snapshot.mode"] == "initial"
    assert "transforms" not in config  # Unwrapping would lose before IDs for deletes/owner changes.
    assert "knowhow.assets.user_id" in config["column.include.list"]
    assert "balance" not in config["column.include.list"]
    assert "password" not in config["column.include.list"]
    assert "user_keyword_id" not in config["column.include.list"]


def test_local_compose_separates_embedding_and_refresh():
    config = yaml.safe_load((ROOT / "docker-compose.cdc.yml").read_text(encoding="utf-8"))
    services = config["services"]
    assert services["persona-worker"]["command"][-1] == "refresh"
    assert services["embedding-worker"]["command"][-1] == "embed"
    assert services["cdc-consumer"]["depends_on"]["register-connector"]["condition"] == "service_completed_successfully"
    assert "cdc-kafka-data:/var/lib/kafka/data" in services["kafka"]["volumes"]
