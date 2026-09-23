from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

MATERIALS = ("Holz", "Eisen", "Bronze", "Silber", "Gold", "Platin", "Diamant")
RANK_IDS = tuple(f"{material}_{stage}" for material in MATERIALS for stage in range(1, 6))


def generate(root: Path) -> None:
    master_dir = root / "master"
    targets = {48: root / "48", 96: root / "96"}
    for directory in targets.values():
        directory.mkdir(parents=True, exist_ok=True)

    missing = [rank_id for rank_id in RANK_IDS if not (master_dir / f"{rank_id}.png").is_file()]
    if missing:
        raise SystemExit("Fehlende Master-Assets: " + ", ".join(missing))

    for rank_id in RANK_IDS:
        source = master_dir / f"{rank_id}.png"
        with Image.open(source) as raw:
            image = raw.convert("RGBA")
            if image.size != (256, 256):
                raise SystemExit(f"{source.name}: erwartet 256x256, gefunden {image.size}")
            for size, directory in targets.items():
                image.resize((size, size), Image.Resampling.LANCZOS).save(
                    directory / source.name,
                    format="PNG",
                    optimize=True,
                )

    print("Rang-Assets erzeugt: 35 Master -> 35x48 + 35x96")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "ranks",
    )
    args = parser.parse_args()
    generate(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
