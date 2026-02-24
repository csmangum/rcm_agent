"""Utility helpers."""

from pathlib import Path


def save_artifact(encounter_id: str, filename: str, content: str, base_dir: str | Path = "data/artifacts") -> Path:
    """
    Write an artifact file to data/artifacts/{encounter_id}/{filename}.
    Returns the path to the written file.
    Ensures content ends with a single newline.
    """
    base = Path(base_dir)
    dir_path = base / encounter_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename
    content = content.rstrip("\n") + "\n"
    file_path.write_text(content, encoding="utf-8")
    return file_path


__all__ = ["save_artifact"]
