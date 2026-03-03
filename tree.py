#!/usr/bin/env python3
# ruff: noqa: RUF001, RUF002, RUF003
"""
tree.py - выводит дерево проекта, исключая мусорные директории и файлы.

Использование:
    python tree.py [путь] [опции]

Опции:
    -c, --show-content       Показывать содержимое файлов (встраивается в дерево, ограничено 10 КБ)
    --full-content           Показывать содержимое файлов без ограничения размера
    --no-size-limit          Отключить ограничение на размер файла (для --show-content и --full-content)
    --content-output FILE    Сохранить только содержимое файлов (без дерева) в указанный файл
    -o, --output FILE        Сохранить полный вывод (дерево + содержимое) в файл

Примеры:
    python tree.py .
    python tree.py . -c
    python tree.py . --full-content --content-out contents.txt
    python tree.py . -c -o tree_with_content.txt
"""

import argparse
import fnmatch
import sys
from contextlib import contextmanager, ExitStack
from pathlib import Path
from typing import List, Optional, TextIO, Tuple, Set

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
    "__init__.py",
    "alembic/versions",
    "ansible",
    "redis/data",
    "script.py.mako",
    "terraform",
    "tree.py",
    "uv.lock",
}

# Максимальный размер файла для вывода содержимого по умолчанию (в байтах)
DEFAULT_MAX_FILE_SIZE = 10 * 1024  # 10 КБ

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
    ".lock",  # бинарный lock-файл (uv.lock уже в игноре, но на всякий случай)
}


@contextmanager
def multi_output(output_files: List[Optional[Path]]) -> Tuple[TextIO, ...]:
    """
    Контекстный менеджер для одновременной записи в несколько файлов (или stdout).
    Возвращает кортеж файловых объектов (потоков) в том же порядке, что и входные пути.
    Если путь None, подставляется sys.stdout.
    """
    files = []
    try:
        for path in output_files:
            if path is None:
                files.append(sys.stdout)
            else:
                # Создаём родительские директории, если нужно
                path.parent.mkdir(parents=True, exist_ok=True)
                files.append(path.open("w", encoding="utf-8"))
        yield tuple(files)
    finally:
        for f in files:
            if f is not sys.stdout:
                f.close()


class IgnoreChecker:
    """Класс для проверки игнорирования файлов с компиляцией паттернов."""

    def __init__(self, ignore_list: Set[str]):
        self.patterns = []  # (type, pattern) type: 'glob', 'dir', 'name'
        self.compile_patterns(ignore_list)

    def compile_patterns(self, ignore_list: Set[str]):
        for pattern in ignore_list:
            if pattern.startswith("*."):
                # Паттерн для суффикса
                suffix = pattern[1:]
                self.patterns.append(('suffix', suffix))
            elif pattern.endswith("/"):
                # Директория (точное совпадение пути с /)
                dir_pattern = pattern.rstrip('/')
                self.patterns.append(('dir_prefix', dir_pattern))
            else:
                # Точное совпадение имени файла или пути
                self.patterns.append(('exact', pattern))

    def should_ignore(self, rel_path: Path) -> bool:
        """Проверяет, нужно ли игнорировать файл/папку по относительному пути."""
        rel_str = str(rel_path).replace("\\", "/")  # унифицируем разделители

        for ptype, pattern in self.patterns:
            if ptype == 'suffix':
                if rel_path.name.endswith(pattern):
                    return True
            elif ptype == 'dir_prefix':
                # Проверяем, является ли rel_path подпапкой pattern
                # или равен pattern
                if rel_str == pattern or rel_str.startswith(pattern + "/"):
                    return True
            elif ptype == 'exact':
                # Точное совпадение пути или имени
                if rel_str == pattern or rel_path.name == pattern:
                    return True
        return False


def read_file_content(
    file_path: Path,
    max_size: Optional[int] = None,
    binary_exts: Set[str] = BINARY_EXTS,
) -> str:
    """
    Читает содержимое файла с обработкой ошибок и опциональным ограничением размера.
    Возвращает текст с отступами (два пробела в начале каждой строки) или сообщение об ошибке.
    """
    try:
        # Проверка на бинарные расширения
        if file_path.suffix.lower() in binary_exts:
            return "  [бинарный файл]"

        # Проверка размера, если задано ограничение
        if max_size is not None:
            try:
                if file_path.stat().st_size > max_size:
                    return f"  [Файл слишком большой (> {max_size // 1024} КБ)]"
            except OSError:
                # Если не можем получить размер, всё равно пытаемся прочитать
                pass

        with file_path.open(encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
            if not lines:
                return "  (пустой файл)"
            # Добавляем отступ ко всем строкам
            return "\n".join(f"  {line}" for line in lines)
    except OSError as e:
        return f"  [Ошибка ввода/вывода: {e}]"
    except UnicodeDecodeError as e:
        return f"  [Ошибка кодировки: {e}]"


def walk_tree(
    dir_path: Path,
    ignore_checker: IgnoreChecker,
    root: Path,
    prefix: str = "",
    show_content: bool = False,
    max_content_size: Optional[int] = DEFAULT_MAX_FILE_SIZE,
    output: Optional[TextIO] = None,
) -> List[Tuple[Path, str]]:
    """
    Рекурсивно обходит дерево и возвращает структуру в виде списка строк.
    Если show_content=True, то для файлов добавляется их содержимое (в виде строк с отступами).
    """
    lines: List[str] = []
    try:
        # Используем .iterdir() и фильтруем
        entries = []
        for p in dir_path.iterdir():
            try:
                rel_path = p.relative_to(root)
            except ValueError:
                # Если путь не относительно root (например, симлинк наружу), используем имя
                rel_path = p.name
            if not ignore_checker.should_ignore(rel_path):
                entries.append(p)

        # Сортируем: сначала папки, потом файлы, по алфавиту без учёта регистра
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
            sub_lines = walk_tree(
                path,
                ignore_checker,
                root,
                prefix + extension,
                show_content,
                max_content_size,
                output,
            )
            lines.extend(sub_lines)
        elif show_content and path.is_file():
            # Читаем содержимое файла с учётом ограничения
            content = read_file_content(path, max_size=max_content_size)
            if content:
                indent = prefix + ("│   " if pointer == "├── " else "    ")
                for line in content.splitlines():
                    lines.append(indent + line)
    return lines


def dump_all_contents(
    dir_path: Path,
    ignore_checker: IgnoreChecker,
    root: Path,
    max_size: Optional[int] = None,
    output: TextIO = sys.stdout,
):
    """
    Выводит содержимое всех файлов (без дерева) в указанный поток.
    Каждый файл предваряется комментарием с путём.
    """
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
            dump_all_contents(path, ignore_checker, root, max_size, output)
        elif path.is_file():
            # Пропускаем бинарные файлы по расширению (можно добавить флаг для их включения)
            if path.suffix.lower() in BINARY_EXTS:
                continue
            # Выводим заголовок файла
            rel_path = path.relative_to(root)
            print(f"\n# Файл: {rel_path}", file=output)
            try:
                # Читаем без ограничения размера (max_size=None) или с ограничением
                with path.open(encoding="utf-8", errors="replace") as f:
                    for line in f:
                        print(line.rstrip(), file=output)
            except (OSError, UnicodeDecodeError) as e:
                print(f"# [Ошибка чтения: {e}]", file=output)


def main():
    parser = argparse.ArgumentParser(
        description="Выводит дерево проекта с опциональным показом содержимого файлов",
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
        "-c",
        "--show-content",
        action="store_true",
        help="Показывать содержимое файлов (встраивается в дерево, ограничено 10 КБ на файл)",
    )
    parser.add_argument(
        "--full-content",
        action="store_true",
        help="Показывать содержимое файлов без ограничения размера (встраивается в дерево)",
    )
    parser.add_argument(
        "--no-size-limit",
        action="store_true",
        help="Отключить ограничение на размер файла (для --show-content и --full-content)",
    )
    parser.add_argument(
        "--content-output",
        type=Path,
        metavar="FILE",
        help="Сохранить только содержимое файлов (без дерева) в указанный файл",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="Сохранить полный вывод (дерево + содержимое) в файл",
    )

    args = parser.parse_args()
    root_path = Path(args.path).resolve()

    if not root_path.exists():
        print(f"Ошибка: путь '{root_path}' не существует.", file=sys.stderr)
        sys.exit(1)

    # Определяем, нужно ли показывать содержимое в дереве и с каким ограничением
    show_content_in_tree = args.show_content or args.full_content
    if args.full_content:
        max_content_size = None  # без ограничения
    elif args.no_size_limit:
        max_content_size = None
    else:
        max_content_size = DEFAULT_MAX_FILE_SIZE

    # Инициализируем проверку игнорирования
    ignore_checker = IgnoreChecker(IGNORE_LIST)

    try:
        # Подготавливаем вывод: может быть несколько потоков (основной вывод и вывод содержимого)
        output_streams = []
        output_paths = []

        # Основной вывод (структура + возможно содержимое)
        if args.output:
            output_paths.append(args.output)
        else:
            output_paths.append(None)  # stdout

        # Дополнительный вывод только содержимого, если указан
        if args.content_output:
            output_paths.append(args.content_output)
        else:
            output_paths.append(None)  # не используется

        with multi_output(output_paths) as (main_out, content_out):
            # Сначала генерируем структуру (если есть куда выводить)
            if args.output or not args.content_output:  # если основной вывод не в никуда
                print("СТРУКТУРА ПРОЕКТА:", file=main_out)
                print(root_path.name + "/", file=main_out)
                tree_lines = walk_tree(
                    root_path,
                    ignore_checker,
                    root_path,
                    show_content=show_content_in_tree,
                    max_content_size=max_content_size,
                )
                for line in tree_lines:
                    print(line, file=main_out)

            # Если нужно отдельно вывести содержимое всех файлов
            if args.content_output and content_out is not sys.stdout:
                print(f"# Содержимое файлов проекта {root_path}", file=content_out)
                dump_all_contents(
                    root_path,
                    ignore_checker,
                    root_path,
                    max_size=None if args.full_content or args.no_size_limit else DEFAULT_MAX_FILE_SIZE,
                    output=content_out,
                )

        # Сообщаем о сохранении
        if args.output:
            print(f"✓ Результат сохранён в {args.output}", file=sys.stderr)
        if args.content_output:
            print(f"✓ Содержимое файлов сохранено в {args.content_output}", file=sys.stderr)

    except OSError as e:
        print(f"Ошибка ввода/вывода: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()