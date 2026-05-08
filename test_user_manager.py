import json
import os

from user_manager import UserManager


def test_user_manager_loads_dict_config_and_cleans_stocks(tmp_path):
    config_path = tmp_path / "users.json"
    config_path.write_text(
        json.dumps(
            {
                "users": [
                    {"name": "Alice", "email": "alice@example.com", "stocks": [" 600519 ", 300750, ""]},
                    {"email": "bob@example.com", "stocks": ["000001"]},
                    {"name": "No Email", "stocks": ["002594"]},
                    {"name": "No Stocks", "email": "empty@example.com", "stocks": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    manager = UserManager(str(config_path))

    users = manager.get_users()
    assert manager.has_users() is True
    assert [user.name for user in users] == ["Alice", "bob"]
    assert [user.email for user in users] == ["alice@example.com", "bob@example.com"]
    assert users[0].stocks == ["600519", "300750"]
    assert manager.get_all_stocks() == {"600519", "300750", "000001"}


def test_user_manager_supports_list_config_and_data_directory_fallback(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "users.json").write_text(
        json.dumps(
            [
                {"name": "Carol", "email": "carol@example.com", "stocks": ["002594"]},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    manager = UserManager()

    assert manager.config_path == os.path.join("data", "users.json")
    assert manager.has_users() is True
    assert manager.get_users()[0].stocks == ["002594"]


def test_user_manager_ignores_missing_malformed_and_invalid_configs(tmp_path):
    missing = UserManager(str(tmp_path / "missing.json"))
    assert missing.has_users() is False
    assert missing.get_all_stocks() == set()

    invalid_shape_path = tmp_path / "invalid_shape.json"
    invalid_shape_path.write_text(json.dumps({"not_users": []}), encoding="utf-8")
    invalid_shape = UserManager(str(invalid_shape_path))
    assert invalid_shape.has_users() is False

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{not json", encoding="utf-8")
    malformed = UserManager(str(malformed_path))
    assert malformed.has_users() is False
