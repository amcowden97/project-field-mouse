from pathlib import Path

from app.web.app import display_storage_path, get_device_information


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


def test_device_information_uses_deployed_cleanup_timer(monkeypatch) -> None:
    requested_services = []

    def service_information(service_name: str) -> dict:
        requested_services.append(service_name)
        return {"name": service_name}

    monkeypatch.setattr(
        "app.web.app.get_service_information",
        service_information,
    )

    device = get_device_information()

    assert "fieldmouse-cleanup.timer" in requested_services
    assert "fieldmouse-storage-manager.timer" not in requested_services
    assert device["services"][-1]["label"] == "Storage cleanup"
