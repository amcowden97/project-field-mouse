from pathlib import Path

from app.web.app import display_storage_path


def test_display_storage_path_uses_relative_project_path(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "release"
    database = project_root / "data" / "fieldmouse.db"

    assert display_storage_path(database, project_root) == str(
        Path("data") / "fieldmouse.db"
    )


def test_display_storage_path_accepts_external_state_path(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "release"
    database = tmp_path / "state" / "fieldmouse.db"

    assert display_storage_path(database, project_root) == str(database)
