#!/usr/bin/env python3
"""Convert the Peppol mapping CSV into JSON and XML files.

The source CSV is semicolon-delimited, has whitespace-padded values and a
trailing empty column. Values and header names are stripped, and empty
columns are dropped.
"""

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

DELIMITER = ","
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "datapublic-peppol-mapping-source.csv"
# Base name for the generated (filtered) output files.
OUTPUT_BASE = "datapublic-peppol-mapping"
# Output file listing data.public.lu organizations that have no Peppol ID.
MISSING_BASE = "organizations-without-peppol-id"

# Relationship types to exclude from the generated output.
EXCLUDED_RELATIONS = {"group", "superset"}
RELATION_KEY = "relation"
UDATA_ID_KEY = "udata_id"
PEPPOL_ID_KEY = "peppol_id"

# Paginated endpoint listing all organizations published on data.public.lu.
ORGANIZATIONS_URL = "https://data.public.lu/api/1/organizations/?page=1&page_size=20"
# Only consider organizations carrying all of these badge "kind" values.
REQUIRED_BADGES = {"certified", "public-service"}


def slugify(name: str) -> str:
    """Turn a header label into a safe XML element / JSON key name."""
    cleaned = [c.lower() if c.isalnum() else "_" for c in name.strip()]
    slug = "".join(cleaned).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "field"


def read_rows(csv_path: Path, apply_filter: bool = True) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh, delimiter=DELIMITER)
        try:
            header = next(reader)
        except StopIteration:
            return []

        # Drop empty trailing columns produced by a trailing delimiter.
        keys = [slugify(col) for col in header]
        keep = [i for i, col in enumerate(header) if col.strip()]

        rows = []
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue  # skip blank lines
            row = {keys[i]: raw[i].strip() if i < len(raw) else "" for i in keep}
            if apply_filter and row.get(RELATION_KEY, "").lower() in EXCLUDED_RELATIONS:
                continue  # filter out group/superset relationships
            rows.append(row)
        return rows


def mapped_udata_ids(csv_path: Path) -> set[str]:
    """udata IDs that already have a (non-empty) Peppol ID, across all relations."""
    return {
        row[UDATA_ID_KEY]
        for row in read_rows(csv_path, apply_filter=False)
        if row.get(UDATA_ID_KEY) and row.get(PEPPOL_ID_KEY)
    }


def fetch_organizations(start_url: str = ORGANIZATIONS_URL) -> list[dict]:
    """Fetch every organization on data.public.lu, following pagination."""
    organizations: list[dict] = []
    url = start_url
    while url:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        for org in payload.get("data", []):
            kinds = {badge.get("kind") for badge in (org.get("badges") or [])}
            if REQUIRED_BADGES <= kinds:
                organizations.append(org)
        url = payload.get("next_page")
    return organizations


def organizations_without_peppol(
    organizations: list[dict], mapped_ids: set[str]
) -> list[dict[str, str]]:
    """Organizations whose udata ID is not present in the mapping."""
    missing = []
    for org in organizations:
        if org.get("id") in mapped_ids:
            continue
        missing.append(
            {
                "udata_id": org.get("id") or "",
                "name": org.get("name") or "",
                "acronym": org.get("acronym") or "",
                "page": org.get("page") or "",
            }
        )
    return missing


def write_json(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    if not rows:
        out_path.write_text("", encoding="utf-8")
        return
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)


def write_xml(rows: list[dict[str, str]], out_path: Path) -> None:
    root = ET.Element("mappings")
    for row in rows:
        entry = ET.SubElement(root, "mapping")
        for key, value in row.items():
            child = ET.SubElement(entry, key)
            child.text = value
    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    out_path.write_bytes(pretty)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv", nargs="?", type=Path, default=DEFAULT_CSV,
        help="Path to the source CSV file.",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=REPO_ROOT,
        help="Directory to write the JSON and XML files into.",
    )
    parser.add_argument(
        "--no-missing", action="store_true",
        help="Skip fetching data.public.lu organizations without a Peppol ID "
             "(avoids the network call).",
    )
    args = parser.parse_args(argv)

    if not args.csv.exists():
        parser.error(f"CSV file not found: {args.csv}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_rows(args.csv)

    json_path = args.output_dir / f"{OUTPUT_BASE}.json"
    xml_path = args.output_dir / f"{OUTPUT_BASE}.xml"
    csv_path = args.output_dir / f"{OUTPUT_BASE}.csv"

    write_json(rows, json_path)
    write_xml(rows, xml_path)
    write_csv(rows, csv_path)

    print(f"Converted {len(rows)} rows")
    print(f"  -> {json_path}")
    print(f"  -> {xml_path}")
    print(f"  -> {csv_path}")

    if not args.no_missing:
        organizations = fetch_organizations()
        missing = organizations_without_peppol(organizations, mapped_udata_ids(args.csv))
        missing_path = args.output_dir / f"{MISSING_BASE}.csv"
        write_csv(missing, missing_path)
        print(
            f"Found {len(missing)} of {len(organizations)} organizations "
            f"without a Peppol ID"
        )
        print(f"  -> {missing_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
