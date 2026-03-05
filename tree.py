#!/usr/bin/env python3
# ruff: noqa: RUF001, RUF002, RUF003
"""
tree.py - выводит дерево проекта и (опционально) содержимое всех файлов.

Использование:
    python tree.py [путь]             # только дерево
    python tree.py [путь] --full-content   # дерево + содержимое всех файлов (без ограничений)

Опции:
    --full-content   Показать содержимое всех файлов после дерева (без ограничения размера)
"""

import argparse
import sys
from pathlib import Path
from typing import List, Set

# Список игнорируемых элементов (можно расширять)
IGNORE_LIST = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".env",
    ".env.local",
    ".env.prod",
    ".DS_Store",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vscode",
    ".idea",
    "*.pyc",
    "*.log",
    "*.tmp",
    "Thumbs.db",
    # "__init__.py",
    "alembic/versions",
    "ansible",
    "redis/data",
    "script.py.mako",
    "terraform",
    "tree.py",
    "uv.lock",
}

# Расширения бинарных файлов, которые не читаем как текст
BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
    ".pyd",
    ".whl",
    ".egg",
    ".lock",
}


class IgnoreChecker:
    """Класс для проверки игнорирования файлов."""

    def __init__(self, ignore_list: Set[str]):
        self.patterns = []
        self.compile_patterns(ignore_list)

    def compile_patterns(self, ignore_list: Set[str]):
        for pattern in ignore_list:
            if pattern.startswith("*."):
                self.patterns.append(('suffix', pattern[1:]))
            elif pattern.endswith("/"):
                self.patterns.append(('dir_prefix', pattern.rstrip('/')))
            else:
                self.patterns.append(('exact', pattern))

    def should_ignore(self, rel_path: Path) -> bool:
        rel_str = str(rel_path).replace("\\", "/")
        for ptype, pat in self.patterns:
            if ptype == 'suffix' and rel_path.name.endswith(pat):
                return True
            if ptype == 'dir_prefix' and (rel_str == pat or rel_str.startswith(pat + "/")):
                return True
            if ptype == 'exact' and (rel_str == pat or rel_path.name == pat):
                return True
        return False


def walk_tree(
    dir_path: Path,
    ignore_checker: IgnoreChecker,
    root: Path,
    prefix: str = "",
) -> List[str]:
    """Рекурсивно обходит дерево и возвращает список строк с его структурой."""
    lines = []
    try:
        entries = []
        for p in dir_path.iterdir():
            try:
                rel_path = p.relative_to(root)
            except ValueError:
                rel_path = p.name
            if not ignore_checker.should_ignore(rel_path):
                entries.append(p)

        entries.sort(key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        lines.append(prefix + "└── [не доступно]")
        return lines

    if not entries:
        return lines

    pointers = ["├── "] * (len(entries) - 1) + ["└── "]
    for pointer, path in zip(pointers, entries):
        lines.append(prefix + pointer + path.name)
        if path.is_dir():
            extension = "│   " if pointer == "├── " else "    "
            lines.extend(walk_tree(path, ignore_checker, root, prefix + extension))
    return lines


def dump_all_contents(
    dir_path: Path,
    ignore_checker: IgnoreChecker,
    root: Path,
):
    """Выводит содержимое всех файлов (без дерева) в stdout."""
    try:
        entries = []
        for p in dir_path.iterdir():
            try:
                rel_path = p.relative_to(root)
            except ValueError:
                rel_path = p.name
            if not ignore_checker.should_ignore(rel_path):
                entries.append(p)

        entries.sort(key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    for path in entries:
        if path.is_dir():
            dump_all_contents(path, ignore_checker, root)
        elif path.is_file():
            # Пропускаем бинарные файлы по расширению
            if path.suffix.lower() in BINARY_EXTS:
                continue
            rel_path = path.relative_to(root)
            print(f"\n# Файл: {rel_path}")
            try:
                with path.open(encoding="utf-8", errors="replace") as f:
                    for line in f:
                        print(line.rstrip())
            except (OSError, UnicodeDecodeError) as e:
                print(f"# [Ошибка чтения: {e}]")


def main():
    parser = argparse.ArgumentParser(
        description="Выводит дерево проекта и (опционально) содержимое всех файлов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Корневая директория (по умолчанию: текущая)",
    )
    parser.add_argument(
        "--full-content",
        action="store_true",
        help="Показать содержимое всех файлов после дерева (без ограничений)",
    )

    args = parser.parse_args()
    root_path = Path(args.path).resolve()

    if not root_path.exists():
        print(f"Ошибка: путь '{root_path}' не существует.", file=sys.stderr)
        sys.exit(1)

    ignore_checker = IgnoreChecker(IGNORE_LIST)

    try:
        # Выводим структуру проекта
        print("СТРУКТУРА ПРОЕКТА:")
        print(root_path.name + "/")
        tree_lines = walk_tree(root_path, ignore_checker, root_path)
        for line in tree_lines:
            print(line)

        # Если запрошено полное содержимое
        if args.full_content:
            print("\nСОДЕРЖИМОЕ ФАЙЛОВ:")
            dump_all_contents(root_path, ignore_checker, root_path)

    except OSError as e:
        print(f"Ошибка ввода/вывода: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()