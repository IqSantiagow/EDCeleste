"""Shows Python files the way the blind-signature-reader agent sees them.

Keeps only classes, method signatures and docstrings. Drops imports, constants,
class attributes and every method body, so a reader can only guess what a method
does from its name, its types and its docstring.

Usage:
    python signature_check/strip_method_bodies.py          # changed against main
    python signature_check/strip_method_bodies.py a.py b.py  # given files
    python signature_check/strip_method_bodies.py --without-docstrings [a.py ...]

--without-docstrings drops the docstrings too, so only the names and the types
are left (stage 1 of the blind-check skill).

Writes the stripped copies to signature_check/stripped/ (same paths as in the
repo, the folder is emptied first) and prints their paths. Pass those paths to
the blind-signature-reader agent. A hook lets that agent read nothing else.
"""

import ast
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_FOLDER = "src/edceleste"
STRIPPED_FOLDER = Path(__file__).parent / "stripped"


def find_changed_python_files() -> list[str]:
    """Committed changes against main, uncommitted changes and new files, only
    Python files under src/edceleste that still exist."""
    git_commands = [
        ["git", "diff", "--name-only", "main...HEAD", "--", SOURCE_FOLDER],
        ["git", "diff", "--name-only", "HEAD", "--", SOURCE_FOLDER],
        ["git", "ls-files", "--others", "--exclude-standard", "--", SOURCE_FOLDER],
    ]
    changed_files: set[str] = set()
    for command in git_commands:
        output = subprocess.run(command, capture_output=True, text=True, check=True)
        changed_files.update(output.stdout.split())

    return sorted(
        file for file in changed_files if file.endswith(".py") and Path(file).exists()
    )


def keep_docstring_only(node: ast.AST) -> list[ast.stmt]:
    """A function without a docstring gets "...", so the reader sees the body is
    gone and there was nothing to keep."""
    docstring = ast.get_docstring(node, clean=False)
    if docstring is None:
        return [ast.Expr(ast.Constant(...))]

    return [ast.Expr(ast.Constant(docstring))]


def keep_classes_and_signatures(body: list[ast.stmt]) -> list[ast.stmt]:
    """Walks one level of a module or a class. Classes go in with their own
    signatures, functions go in with only their docstring, the rest is dropped."""
    kept: list[ast.stmt] = []
    for node in body:
        if isinstance(node, ast.ClassDef):
            class_docstring = ast.get_docstring(node, clean=False)
            node.body = keep_classes_and_signatures(node.body)
            if class_docstring is not None:
                node.body.insert(0, ast.Expr(ast.Constant(class_docstring)))
            if not node.body:
                node.body = [ast.Expr(ast.Constant(...))]
            kept.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.body = keep_docstring_only(node)
            kept.append(node)

    return kept


def remove_docstrings(module: ast.Module) -> None:
    """Runs on the already stripped module, so every function body is just its
    docstring or "...". Module and class docstrings are removed as well."""
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.body = [ast.Expr(ast.Constant(...))]
        elif isinstance(node, (ast.Module, ast.ClassDef)):
            if ast.get_docstring(node, clean=False) is not None:
                node.body = node.body[1:] or [ast.Expr(ast.Constant(...))]


def strip_method_bodies(source_code: str, keep_docstrings: bool = True) -> str:
    """Comments are lost too, ast does not keep them. Decorators stay, they are
    part of the signature."""
    module = ast.parse(source_code)
    module_docstring = ast.get_docstring(module, clean=False)
    module.body = keep_classes_and_signatures(module.body)
    if module_docstring is not None:
        module.body.insert(0, ast.Expr(ast.Constant(module_docstring)))
    if not keep_docstrings:
        remove_docstrings(module)

    return ast.unparse(module)


def main() -> None:
    """Files without any function (plain models, constants) are skipped, there
    is nothing to guess in them. Copies from an earlier run are deleted, so the
    agent never reads a stale file."""
    arguments = sys.argv[1:]
    keep_docstrings = "--without-docstrings" not in arguments
    files = [argument for argument in arguments if argument != "--without-docstrings"]
    files = files or find_changed_python_files()
    shutil.rmtree(STRIPPED_FOLDER, ignore_errors=True)
    if not files:
        print("No changed Python files under src/edceleste.")
        return

    for file in files:
        source_code = Path(file).read_text(encoding="utf-8")
        stripped_code = strip_method_bodies(source_code, keep_docstrings)
        if "def " not in stripped_code:
            continue
        stripped_file = STRIPPED_FOLDER / file
        stripped_file.parent.mkdir(parents=True, exist_ok=True)
        stripped_file.write_text(stripped_code + "\n", encoding="utf-8")
        print(stripped_file.resolve().as_posix())


if __name__ == "__main__":
    main()
