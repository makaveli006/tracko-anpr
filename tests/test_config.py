import os
from pathlib import Path

from tracko_anpr.config import build_database_url, find_project_root, load_settings, read_env_file


def test_project_root_is_the_folder_with_pyproject():
    root = find_project_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "tracko_anpr").is_dir()


def test_env_file_parsing_skips_comments_and_strips_quotes(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# a comment\n\nPOSTGRES_USER=tracko\nPOSTGRES_PASSWORD="p@ss word"\nNOT A PAIR\nEMPTY=\n',
        encoding="utf-8",
    )
    assert read_env_file(env_file) == {"POSTGRES_USER": "tracko", "POSTGRES_PASSWORD": "p@ss word", "EMPTY": ""}


def test_missing_env_file_gives_no_values(tmp_path: Path):
    assert read_env_file(tmp_path / "absent.env") == {}


def test_database_url_uses_psycopg_and_escapes_the_password():
    url = build_database_url({"POSTGRES_USER": "tracko", "POSTGRES_PASSWORD": "p@ss/word", "POSTGRES_DB": "demo"})
    assert url == "postgresql+psycopg://tracko:p%40ss%2Fword@127.0.0.1:5432/demo"


def test_explicit_database_url_wins():
    assert build_database_url({"TRACKO_DATABASE_URL": "postgresql+psycopg://x/y", "POSTGRES_USER": "ignored"}) == (
        "postgresql+psycopg://x/y"
    )


def test_settings_paths_sit_under_the_root_and_env_overrides_apply(tmp_path: Path):
    settings = load_settings(root=tmp_path, environ={"TRACKO_VEHICLE_IMAGE_SIZE": "1280"})
    assert settings.vehicle_weights == tmp_path / "models" / "yolo26m.pt"
    assert settings.ocr_model == tmp_path / "models" / "awiros" / "model.safetensors"
    assert settings.processed_dir == tmp_path / "storage" / "processed"
    assert settings.vehicle_image_size == 1280
    assert settings.vehicle_confidence == 0.1


def test_env_file_is_read_but_real_environment_wins(tmp_path: Path):
    (tmp_path / ".env").write_text("TRACKO_VEHICLE_IMAGE_SIZE=960\nPOSTGRES_DB=from_file\n", encoding="utf-8")
    from_file = load_settings(root=tmp_path, environ={})
    assert from_file.vehicle_image_size == 960
    assert from_file.database_url.endswith("/from_file")

    overridden = load_settings(root=tmp_path, environ={"TRACKO_VEHICLE_IMAGE_SIZE": "640"})
    assert overridden.vehicle_image_size == 640


def test_importing_the_package_turns_off_ultralytics_auto_install():
    import tracko_anpr  # noqa: F401

    assert os.environ["YOLO_AUTOINSTALL"] == "False"
