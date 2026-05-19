from __future__ import annotations

from pathlib import Path


def main() -> None:
    p = Path(".env")
    if not p.exists():
        raise SystemExit("No .env found in project root.")

    keys: dict[str, int] = {}
    raw: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        keys[k] = len(v)
        raw[k] = v

    for k in sorted(keys):
        print(f"{k} length={keys[k]}")

    # Helpful for debugging non-secret fields
    if "DEEPSEEK_BASE_URL" in raw:
        print("DEEPSEEK_BASE_URL value:", raw["DEEPSEEK_BASE_URL"])


if __name__ == "__main__":
    main()

