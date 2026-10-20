"""导出无Git历史的公开快照；白名单、凭据/个人资料检查在写入前完成。"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT_FILES = {
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "AGENTS.md",
    "Makefile",
    ".gitignore",
    ".editorconfig",
    ".prettierignore",
}
BACKEND_FILES = {
    "README.md",
    "AGENTS.md",
    ".gitignore",
    ".env.example",
    "Dockerfile",
    ".dockerignore",
    "alembic.ini",
    "pyproject.toml",
    ".python-version",
    "uv.lock",
    "compose.yaml",
}
DOC_FILES = {"docs/部署指南.md", "docs/开源说明.md"}
PRIVATE = re.compile(
    rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----|"
    rb"\b(?:sk-[A-Za-z0-9_-]{24,}|lsv2_[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})\b|"
    rb"[A-Za-z0-9._%+-]+@(?:gmail|qq|163|126|outlook|icloud|foxmail)\.com\b|"
    rb"139\.224\.26\.159|api\.soberism\.top|/(?:Users|home)/[A-Za-z0-9_.-]+/"
)


def included(name):
    path = Path(name)
    parts = path.parts
    if any(
        part
        in {
            ".git",
            ".local",
            ".venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "test-results",
            "playwright-report",
        }
        for part in parts
    ):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix in {".pem", ".key", ".log", ".pyc", ".har"}:
        return False
    if name in ROOT_FILES or name in DOC_FILES or name.startswith(".github/workflows/"):
        return True
    if name.startswith(
        (
            "backend/src/",
            "backend/migrations/",
            "frontend/src/",
            "frontend/public/",
            "frontend/tests/",
        )
    ):
        return True
    if name.startswith("backend/tests/"):
        return not name.startswith("backend/tests/results/")
    if name.startswith("backend/infra/"):
        return path.suffix in {".py", ".sh", ".sql", ".conf", ".yaml"}
    if name.startswith(
        (
            "backend/openspec/specs/",
            "frontend/openspec/specs/",
            "backend/openspec/changes/prepare-public-release/",
            "frontend/openspec/changes/prepare-public-release/",
        )
    ):
        return True
    if len(parts) == 2 and parts[0] == "backend":
        return parts[1] in BACKEND_FILES
    if len(parts) == 2 and parts[0] == "frontend":
        return path.suffix in {".json", ".ts", ".js", ".html"} or parts[1] in {
            "README.md",
            "AGENTS.md",
            ".gitignore",
        }
    return False


def export(root, destination):
    root, destination = root.resolve(), destination.absolute()
    if destination.exists() or destination.resolve().is_relative_to(root):
        raise ValueError("目标必须是仓库外尚不存在的目录")
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        if not included(name):
            continue
        source = root / name
        if not source.exists():
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f"拒绝符号链接或越界路径：{name}")
        if source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(f"需人工检查的大文件：{name}")
        data = source.read_bytes()
        if b"\0" not in data[:1024] and PRIVATE.search(data):
            raise ValueError(f"发现需脱敏的内容（不显示原文）：{name}")
        files[name] = data
    for required in (
        "README.md",
        "LICENSE",
        "backend/pyproject.toml",
        "frontend/package-lock.json",
    ):
        if required not in files:
            raise ValueError(f"缺少公开版本必要文件：{required}")
    destination.mkdir(parents=True)
    manifest = {}
    for name, data in sorted(files.items()):
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        if name.endswith(".sh"):
            output.chmod(0o755)
        manifest[name] = hashlib.sha256(data).hexdigest()
    (destination / "PUBLIC_EXPORT.json").write_text(
        json.dumps({"files": manifest}, ensure_ascii=False, indent=2) + "\n"
    )
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = export(Path(__file__).resolve().parents[2], args.destination)
    print(f"已导出{count}个文件；未复制Git历史、环境凭据、调研归档或测试结果。")


if __name__ == "__main__":
    main()
