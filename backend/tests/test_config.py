"""환경변수 파일 인코딩 처리 테스트 (DB 불필요)."""
import importlib
import os

import pytest

LINE = "DATABASE_URL=postgresql://u:p@h:5432/db\n"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_env_file_encodings(tmp_path, monkeypatch, encoding):
    f = tmp_path / ".env"
    f.write_bytes(("# 주석\n" + LINE).encode(encoding) if encoding != "utf-16" else ("# 주석\n" + LINE).encode("utf-16"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app import config
    monkeypatch.setattr(config, "ENV_FILES", [f])
    config._LOADED = config._load_env()
    assert config.database_url() == "postgresql+psycopg://u:p@h:5432/db"
    os.environ.pop("DATABASE_URL", None)


def test_missing_url_message_lists_names_not_values(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("OTHER_NAME=secretvalue\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app import config
    monkeypatch.setattr(config, "ENV_FILES", [f])
    config._LOADED = config._load_env()
    with pytest.raises(RuntimeError) as e:
        config.database_url()
    assert "OTHER_NAME" in str(e.value) and "secretvalue" not in str(e.value)
    os.environ.pop("OTHER_NAME", None)
