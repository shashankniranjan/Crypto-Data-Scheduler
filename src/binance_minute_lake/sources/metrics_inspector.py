from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


class MetricsZipInspector:
    @staticmethod
    def list_columns(zip_path: Path) -> list[str]:
        with zipfile.ZipFile(zip_path, mode="r") as archive:
            csv_files = [name for name in archive.namelist() if name.endswith(".csv")]
            if not csv_files:
                raise ValueError(f"No CSV file found inside {zip_path}")
            with archive.open(csv_files[0], mode="r") as handle:
                text_stream = io.TextIOWrapper(handle, encoding="utf-8")
                reader = csv.reader(text_stream)
                try:
                    return next(reader)
                except StopIteration as exc:
                    raise ValueError(f"CSV in {zip_path} is empty") from exc
