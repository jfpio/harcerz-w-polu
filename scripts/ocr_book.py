#!/usr/bin/env python3
"""Checkpointed Mistral OCR pipeline for the Harcerz w polu scan."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


API_ROOT = "https://api.mistral.ai/v1"
SOURCE_URL = "https://polona.pl/item-view/0782bd3a-4d20-41be-86f8-bcdfc65555c5?page=0"
DEFAULT_ENV = Path.home() / ".secrets" / "mistral.env"


def load_api_key(env_path: Path) -> str:
    if not env_path.exists():
        raise SystemExit(f"Missing Mistral environment file: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        name, separator, value = line.partition("=")
        if separator and name.strip() == "MISTRAL_API_KEY":
            return value.strip().strip("'\"")
    raise SystemExit("MISTRAL_API_KEY is not defined in the environment file")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def curl_json(
    api_key: str,
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    form: list[str] | None = None,
    attempts: int = 8,
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, attempts + 1):
        with tempfile.NamedTemporaryFile(suffix=".json") as output_file:
            command = [
                "curl",
                "--fail-with-body",
                "--silent",
                "--show-error",
                "--request",
                method,
                url,
                "--header",
                f"Authorization: Bearer {api_key}",
                "--output",
                output_file.name,
            ]
            payload_file: tempfile.NamedTemporaryFile[str] | None = None
            try:
                if payload is not None:
                    payload_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8")
                    json.dump(payload, payload_file, ensure_ascii=False)
                    payload_file.flush()
                    command.extend(
                        [
                            "--header",
                            "Content-Type: application/json",
                            "--data-binary",
                            f"@{payload_file.name}",
                        ]
                    )
                for item in form or []:
                    command.extend(["--form", item])
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                output_file.seek(0)
                body = output_file.read().decode("utf-8", errors="replace")
                if result.returncode == 0:
                    return json.loads(body)
                last_error = body or result.stderr.strip() or f"curl exit code {result.returncode}"
            finally:
                if payload_file is not None:
                    payload_file.close()
        if attempt < attempts:
            if "rate limit" in last_error.lower() or '"code":"1300"' in last_error:
                time.sleep(min(15 * attempt, 45))
            else:
                time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"Mistral API request failed after {attempts} attempts: {last_error[:1000]}")


def upload_pdf(api_key: str, pdf_path: Path) -> dict[str, Any]:
    return curl_json(
        api_key,
        "POST",
        f"{API_ROOT}/files",
        form=["purpose=ocr", f"file=@{pdf_path};type=application/pdf"],
    )


def get_signed_url(api_key: str, file_id: str) -> str:
    response = curl_json(api_key, "GET", f"{API_ROOT}/files/{file_id}/url?expiry=24")
    return str(response["url"])


def delete_upload(api_key: str, file_id: str) -> bool:
    response = curl_json(api_key, "DELETE", f"{API_ROOT}/files/{file_id}")
    return bool(response.get("deleted"))


def save_json_gzip(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def safe_asset_name(page_index: int, image_id: str, media_type: str) -> str:
    source_name = Path(image_id).name
    suffix = Path(source_name).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(media_type) or ".bin"
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(source_name).stem).strip("-") or "image"
    return f"page-{page_index + 1:03d}-{stem}{suffix.lower()}"


def extract_images(response: dict[str, Any], asset_dir: Path) -> int:
    asset_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for page in response.get("pages", []):
        page_index = int(page["index"])
        for image in page.get("images", []):
            encoded = image.get("image_base64")
            if not encoded:
                continue
            media_type = "application/octet-stream"
            if encoded.startswith("data:"):
                header, encoded = encoded.split(",", 1)
                media_type = header[5:].split(";", 1)[0]
            target = asset_dir / safe_asset_name(page_index, str(image.get("id", "image")), media_type)
            target.write_bytes(base64.b64decode(encoded))
            written += 1
    return written


def chunk_ranges(total_pages: int, chunk_size: int) -> list[tuple[int, int]]:
    return [
        (start, min(start + chunk_size - 1, total_pages - 1))
        for start in range(0, total_pages, chunk_size)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output", type=Path, default=Path("data/ocr"))
    parser.add_argument("--assets", type=Path, default=Path("public/book/assets"))
    parser.add_argument("--pages", type=int, default=260)
    parser.add_argument("--chunk-size", type=int, default=20)
    parser.add_argument("--model", default="mistral-ocr-4-1")
    parser.add_argument("--file-id")
    parser.add_argument("--keep-upload", action="store_true")
    parser.add_argument("--chunk-delay", type=float, default=25.0)
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    api_key = load_api_key(args.env)
    manifest_path = args.output / "manifest.json"
    manifest = load_json(manifest_path)
    manifest.update(
        {
            "schemaVersion": 1,
            "source": {
                "title": "Harcerz w polu: zabawy i gry terenowe",
                "author": "Zygmunt Wyrobek",
                "edition": 5,
                "publicationPlace": "Kraków",
                "publicationYear": 1946,
                "polonaUrl": SOURCE_URL,
                "rightsStatement": "Domena publiczna (oznaczenie rekordu Polony)",
                "accessedOn": date.today().isoformat(),
                "pdfFilename": pdf_path.name,
                "pdfSha256": sha256_file(pdf_path),
                "pdfBytes": pdf_path.stat().st_size,
                "pdfPages": args.pages,
            },
            "ocr": {
                "requestedModel": args.model,
                "includeBlocks": True,
                "includeImageBase64": True,
                "extractHeader": True,
                "extractFooter": True,
                "confidenceScoresGranularity": "word",
                "chunkSize": args.chunk_size,
            },
            "chunks": manifest.get("chunks", []),
        }
    )

    file_id = args.file_id or manifest.get("upload", {}).get("fileId")
    if not file_id:
        upload = upload_pdf(api_key, pdf_path)
        file_id = str(upload["id"])
        manifest["upload"] = {
            "fileId": file_id,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "bytes": upload.get("bytes"),
            "deleted": False,
        }
        write_json(manifest_path, manifest)
    else:
        manifest["upload"] = {
            **manifest.get("upload", {}),
            "fileId": file_id,
            "deleted": False,
        }
        write_json(manifest_path, manifest)

    signed_url = get_signed_url(api_key, file_id)
    completed = {(int(item["start"]), int(item["end"])) for item in manifest.get("chunks", [])}
    actual_models: set[str] = set(manifest.get("ocr", {}).get("actualModels", []))

    try:
        for start, end in chunk_ranges(args.pages, args.chunk_size):
            chunk_path = args.output / "chunks" / f"pages-{start:03d}-{end:03d}.json.gz"
            if (start, end) in completed and chunk_path.exists():
                print(f"skip {start:03d}-{end:03d}: checkpoint exists", flush=True)
                continue

            payload = {
                "model": args.model,
                "document": {"type": "document_url", "document_url": signed_url},
                "pages": f"{start}-{end}",
                "include_blocks": True,
                "include_image_base64": True,
                "extract_header": True,
                "extract_footer": True,
                "confidence_scores_granularity": "word",
            }
            print(f"ocr {start:03d}-{end:03d}", flush=True)
            response = curl_json(api_key, "POST", f"{API_ROOT}/ocr", payload=payload)
            expected = end - start + 1
            if len(response.get("pages", [])) != expected:
                raise RuntimeError(
                    f"Chunk {start}-{end} returned {len(response.get('pages', []))} pages, expected {expected}"
                )
            save_json_gzip(chunk_path, response)
            image_count = extract_images(response, args.assets)
            actual_models.add(str(response.get("model", args.model)))
            manifest["chunks"] = [
                item
                for item in manifest.get("chunks", [])
                if (int(item["start"]), int(item["end"])) != (start, end)
            ]
            manifest["chunks"].append(
                {
                    "start": start,
                    "end": end,
                    "pages": expected,
                    "images": image_count,
                    "file": str(chunk_path),
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                    "usage": response.get("usage_info", {}),
                }
            )
            manifest["chunks"].sort(key=lambda item: int(item["start"]))
            manifest["ocr"]["actualModels"] = sorted(actual_models)
            write_json(manifest_path, manifest)
            if end < args.pages - 1 and args.chunk_delay > 0:
                time.sleep(args.chunk_delay)

        manifest["completedAt"] = datetime.now(timezone.utc).isoformat()
        manifest["pageCoverage"] = list(range(args.pages))
        if not args.keep_upload:
            manifest["upload"]["deleted"] = delete_upload(api_key, file_id)
            manifest["upload"]["deletedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
        print(f"complete: {args.pages} pages", flush=True)
    except Exception:
        manifest["interruptedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    main()
