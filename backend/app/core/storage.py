from pathlib import Path

STORAGE_DIRECTORIES = ("uploads", "exports", "workspace")


def ensure_storage_directories(storage_root: Path) -> None:
    for directory in STORAGE_DIRECTORIES:
        (storage_root / directory).mkdir(parents=True, exist_ok=True)


def check_storage(storage_root: Path) -> tuple[bool, str | None]:
    try:
        ensure_storage_directories(storage_root)
        for directory in STORAGE_DIRECTORIES:
            path = storage_root / directory
            if not path.is_dir():
                return False, f"Storage directory is unavailable: {directory}"
        return True, None
    except OSError:
        return False, "Storage directory could not be prepared"
