import json
import os
import site
import shutil
import subprocess
import sys
from pathlib import Path

import constants

ROOT = Path(__file__).resolve().parent
VERSION_SLUG = str(constants.APP_VERSION).replace(".", "_")
APP_NAME = f"AccessDBToolPortable_v{VERSION_SLUG}"
DIST_DIR = ROOT / "dist" / APP_NAME
BUILD_DIR = ROOT / "build"
ENTRYPOINT = ROOT / "access_db_tool.pyw"
VENDOR_DIR = ROOT / "_vendor"
HOOKS_DIR = ROOT / "pyinstaller_hooks"

STATE_FILES = {
    "saved_conditions.json": [],
    "condition_groups.json": {},
    "database_registry.json": {},
    "monitor_log.json": [],
}


def get_user_site():
    try:
        return Path(site.getusersitepackages())
    except Exception:
        return None


def get_extra_python_paths():
    paths = []
    if VENDOR_DIR.exists():
        paths.append(VENDOR_DIR)
    user_site = get_user_site()
    if os.environ.get("ACCESSDBTOOL_INCLUDE_USER_SITE") == "1" and user_site and user_site.exists():
        paths.append(user_site)
    return paths


def ensure_pyinstaller_on_path():
    for path in get_extra_python_paths():
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.append(path_str)


def ensure_state_files():
    for name, default_data in STATE_FILES.items():
        path = ROOT / name
        if path.exists():
            continue
        with path.open("w", encoding="utf-8") as fh:
            json.dump(default_data, fh, indent=2, ensure_ascii=False)


def run_pyinstaller():
    env = os.environ.copy()
    extra_paths = [str(path) for path in get_extra_python_paths()]
    if extra_paths:
        current = env.get("PYTHONPATH", "")
        joined = os.pathsep.join(extra_paths)
        env["PYTHONPATH"] = joined if not current else joined + os.pathsep + current
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller.__main__",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        APP_NAME,
        "--additional-hooks-dir",
        str(HOOKS_DIR),
        # ttkbootstrap carica asset grafici (PNG/ICO per checkbox, progressbar,
        # icona app) e temi via import dinamici: PyInstaller non li include da
        # solo, senza --collect-all l'exe perde immagini e temi.
        "--collect-all",
        "ttkbootstrap",
        str(ENTRYPOINT),
    ]
    for path in extra_paths:
        cmd.extend(["--paths", path])
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)


def copy_portable_state():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        shutil.copy2(ROOT / name, DIST_DIR / name)


def write_launcher():
    launcher = DIST_DIR / "Avvia_AccessDBToolPortable.cmd"
    launcher.write_text(
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        f"start \"\" \"{APP_NAME}.exe\"\r\n",
        encoding="utf-8",
    )


def write_readme():
    readme = DIST_DIR / "README_PORTABLE.txt"
    readme.write_text(
        f"ACCESS DB TOOL PORTABLE v{constants.APP_VERSION}\r\n"
        "================================\r\n\r\n"
        "Avvio:\r\n"
        f"- Esegui {APP_NAME}.exe dalla cartella corrente.\r\n\r\n"
        "File persistenti mantenuti accanto all'exe:\r\n"
        "- saved_conditions.json\r\n"
        "- condition_groups.json\r\n"
        "- database_registry.json\r\n"
        "- monitor_log.json\r\n"
        "- app.log\r\n\r\n"
        "Nota importante:\r\n"
        "Il tool richiede un driver ODBC Microsoft Access installato sul PC target.\r\n",
        encoding="utf-8",
    )


def main():
    ensure_pyinstaller_on_path()
    try:
        import PyInstaller  # noqa: F401
    except ModuleNotFoundError:
        print("PyInstaller non installato.")
        print("Installa con: python -m pip install pyinstaller")
        return 1

    ensure_state_files()

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    run_pyinstaller()
    copy_portable_state()
    write_launcher()
    write_readme()

    print(f"Build completata in: {DIST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
