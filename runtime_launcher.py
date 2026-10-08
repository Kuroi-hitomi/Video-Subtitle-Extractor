"""Start the application using its verified runtime."""
import subprocess
import sys

from runtime_config import APP, active_environment, clean_environment


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action != "start":
        raise ValueError("This runtime-only installation supports the start action.")
    environment = active_environment()
    python = environment / "Scripts" / "python.exe"
    env = clean_environment()
    if not python.is_file():
        raise RuntimeError("The configured runtime is missing. Restore the environment named in runtime.json.")
    subprocess.run([str(python), "-X", "utf8", str(APP / "app.py")], cwd=APP, env=env, check=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        sys.exit(1)
