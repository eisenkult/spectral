import sys
from pathlib import Path
from app import SpectralApp


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <folder>")
        sys.exit(1)

    folder = sys.argv[1]
    if not Path(folder).is_dir():
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)

    app = SpectralApp(folder)
    app.run()


if __name__ == "__main__":
    main()
