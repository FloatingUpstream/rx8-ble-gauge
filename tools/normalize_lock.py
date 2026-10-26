"""Remove local machine paths from the committed IDF dependency lock."""

from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    lock = root / "firmware" / "dependencies.lock"
    if lock.exists():
        text = lock.read_text()
        normalized = text.replace(f"path: {root}/third_party/", "path: ${GAUGE_ROOT}/third_party/")
        if normalized != text:
            lock.write_text(normalized)


if __name__ == "__main__":
    main()
