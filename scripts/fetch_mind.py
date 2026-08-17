#!/usr/bin/env python3
"""Download a MIND release without checking raw data into this repository."""

from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from pathlib import Path

URLS = {
    ("small", "train"): "https://mind201910small.blob.core.windows.net/release/MINDsmall_train.zip",
    ("small", "dev"): "https://mind201910small.blob.core.windows.net/release/MINDsmall_dev.zip",
    ("large", "train"): "https://mind201910large.blob.core.windows.net/release/MINDlarge_train.zip",
    ("large", "dev"): "https://mind201910large.blob.core.windows.net/release/MINDlarge_dev.zip",
}


def normalise_dataset_root(target: Path) -> None:
    """Flatten the single wrapper directory used by official MIND archives."""
    if (target / "news.tsv").is_file() and (target / "behaviors.tsv").is_file():
        return
    wrappers = [
        child
        for child in target.iterdir()
        if child.is_dir() and (child / "news.tsv").is_file() and (child / "behaviors.tsv").is_file()
    ]
    if len(wrappers) != 1:
        raise SystemExit(f"error: could not find one MIND dataset root below {target}")
    wrapper = wrappers[0]
    for child in wrapper.iterdir():
        shutil.move(str(child), target / child.name)
    wrapper.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("small", "large"), required=True)
    parser.add_argument("--split", choices=("train", "dev"), required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="An authorised replacement URL for the requested archive")
    source.add_argument("--archive", type=Path, help="A locally acquired MIND zip archive")
    arguments = parser.parse_args()
    name = f"MIND{arguments.dataset}_{arguments.split}"
    target = arguments.data_dir / name
    archive = arguments.data_dir / f"{name}.zip"
    if target.exists() and (target / "news.tsv").exists() and (target / "behaviors.tsv").exists():
        print(f"{target} already exists; nothing to download.")
        return 0
    arguments.data_dir.mkdir(parents=True, exist_ok=True)
    if arguments.archive:
        if not arguments.archive.is_file():
            raise SystemExit(f"error: archive does not exist: {arguments.archive}")
        shutil.copyfile(arguments.archive, archive)
    else:
        source_url = arguments.url or URLS[(arguments.dataset, arguments.split)]
        print(f"Downloading {name}...")
        try:
            with urllib.request.urlopen(source_url) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        except Exception as error:
            archive.unlink(missing_ok=True)
            raise SystemExit(
                "error: the download was unavailable. Microsoft currently restricts unauthenticated "
                "access to the legacy blob endpoint. Obtain MIND through an authorised distribution, "
                "then rerun with --archive PATH or --url AUTHORISED_URL. "
                f"Underlying error: {error}"
            ) from error
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(target)
    archive.unlink()
    normalise_dataset_root(target)
    print(f"Extracted {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
