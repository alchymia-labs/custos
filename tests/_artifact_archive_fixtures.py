from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import zipfile
from pathlib import Path


def _record_hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def regular_zip_info(name: str, *, compress_type: int = zipfile.ZIP_STORED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = compress_type
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def write_test_wheel(
    path: Path,
    *,
    extra_entries: list[tuple[zipfile.ZipInfo, bytes]] | None = None,
    module_payload: bytes = b"class RuntimeAdapter:\n    pass\n",
    entry_point: str = "strategies.supertrend:RuntimeAdapter",
    entry_point_group: str = "alephain.strategy_runtime.v1",
    record_digest_override: str | None = None,
    compression: int = zipfile.ZIP_STORED,
) -> None:
    dist_info = "supertrend-1.0.0.dist-info"
    entries: list[tuple[zipfile.ZipInfo, bytes]] = [
        (regular_zip_info("strategies/__init__.py", compress_type=compression), b""),
        (
            regular_zip_info("strategies/supertrend.py", compress_type=compression),
            module_payload,
        ),
        (
            regular_zip_info(f"{dist_info}/entry_points.txt", compress_type=compression),
            (f"[{entry_point_group}]\nsupertrend = {entry_point}\n").encode(),
        ),
        (
            regular_zip_info(f"{dist_info}/WHEEL", compress_type=compression),
            b"Wheel-Version: 1.0\nGenerator: custos-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        ),
        (
            regular_zip_info(f"{dist_info}/METADATA", compress_type=compression),
            b"Metadata-Version: 2.3\nName: supertrend\nVersion: 1.0.0\n",
        ),
    ]
    entries.extend(extra_entries or [])

    record_rows: list[list[str]] = []
    for info, payload in entries:
        digest = record_digest_override or _record_hash(payload)
        record_rows.append([info.filename, digest, str(len(payload))])
    record_name = f"{dist_info}/RECORD"
    record_rows.append([record_name, "", ""])
    record_stream = io.StringIO(newline="")
    csv.writer(record_stream, lineterminator="\n").writerows(record_rows)
    entries.append((regular_zip_info(record_name), record_stream.getvalue().encode()))

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info, payload in entries:
            archive.writestr(info, payload)
