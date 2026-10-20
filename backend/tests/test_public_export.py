"""公开快照使用白名单，预检失败不留下部分敏感文件。"""

import json
import subprocess
from pathlib import Path
from runpy import run_path

import pytest

module = run_path(str(Path(__file__).resolve().parents[1] / "infra/export_public.py"))
included, export = module["included"], module["export"]


@pytest.mark.parametrize(
    "name",
    [
        "backend/.env",
        "backend/.env.local",
        "backend/.local/id_ed25519",
        "docs/archive/ohai/experience.txt",
        "docs/assets/account.png",
        "backend/tests/results/run.jsonl",
        ".git/config",
        "frontend/node_modules/a.js",
        "backend/src/credential.pem",
    ],
)
def test_private_material_is_never_selected(name):
    assert not included(name)


def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in (
        "README.md",
        "LICENSE",
        "backend/pyproject.toml",
        "frontend/package-lock.json",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    return root


def test_export_has_no_history_or_private_archive_and_has_hashes(tmp_path):
    root = repository(tmp_path)
    (root / "backend/.env").write_text("PRIVATE_CONFIG=synthetic")
    (root / "docs/archive").mkdir(parents=True)
    (root / "docs/archive/private.txt").write_text("private")
    target = tmp_path / "public"
    assert export(root, target) == 4
    assert not (target / ".git").exists() and not (target / "backend/.env").exists()
    assert not (target / "docs/archive").exists()
    manifest = json.loads((target / "PUBLIC_EXPORT.json").read_text())
    assert len(manifest["files"]) == 4
    assert len(manifest["files"]["README.md"]) == 64
    with pytest.raises(ValueError):
        export(root, target)


def test_detected_personal_information_blocks_before_writing(tmp_path):
    root = repository(tmp_path)
    (root / "README.md").write_text("synthetic-user" + "@gmail.com")
    target = tmp_path / "public"
    with pytest.raises(ValueError, match="README.md"):
        export(root, target)
    assert not target.exists()


def test_symlink_cannot_smuggle_private_content(tmp_path):
    root = repository(tmp_path)
    secret = tmp_path / "private.txt"
    secret.write_text("private")
    (root / "README.md").unlink()
    (root / "README.md").symlink_to(secret)
    with pytest.raises(ValueError, match="符号链接"):
        export(root, tmp_path / "public")
