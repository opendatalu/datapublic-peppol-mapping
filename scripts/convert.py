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
# Output file listing source rows with an ID unknown to its reference API.
UNKNOWN_BASE = "unknown-ids"
# Output file listing source rows whose name differs from its reference API.
MISMATCH_BASE = "name-mismatches"

# Relationship types to exclude from the generated output.
EXCLUDED_RELATIONS = {"group", "superset"}
RELATION_KEY = "relation"
UDATA_ID_KEY = "udata_id"
UDATA_NAME_KEY = "udata_name"
PEPPOL_ID_KEY = "peppol_id"
PEPPOL_NAME_KEY = "peppol_name"
# Extra column added to the check outputs telling which side the issue is on.
ISSUE_SOURCE_KEY = "issue_source"
UDATA_SOURCE = "data.public.lu"
PEPPOL_SOURCE = "Peppol"

# Paginated endpoint listing all organizations published on data.public.lu.
ORGANIZATIONS_URL = "https://data.public.lu/api/1/organizations/?page=1&page_size=20"
# Only consider organizations carrying all of these badge "kind" values.
REQUIRED_BADGES = {"certified", "public-service"}

# JSON feed listing every Peppol partner (id + name).
PEPPOL_PARTNERS_URL = (
    "https://data.public.lu/fr/datasets/r/b5cf16d5-83ae-4154-9abf-b339c95ef100"
)


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
        organizations.extend(payload.get("data", []))
        url = payload.get("next_page")
    return organizations


def has_required_badges(org: dict) -> bool:
    """True when an organization carries all of the REQUIRED_BADGES kinds."""
    kinds = {badge.get("kind") for badge in (org.get("badges") or [])}
    return REQUIRED_BADGES <= kinds


def fetch_peppol_partners(url: str = PEPPOL_PARTNERS_URL) -> dict[str, str]:
    """Fetch the Peppol partner directory as an ``{id: name}`` mapping."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    return {
        partner["id"]: (partner.get("name") or "").strip()
        for partner in payload.get("partners", [])
        if partner.get("id")
    }


def unknown_id_rows(
    rows: list[dict[str, str]],
    udata_ids: set[str],
    peppol_ids: set[str],
) -> list[dict[str, str]]:
    """Source rows carrying an ID that its reference API does not know.

    A single source row may yield two entries (one per side) when both its
    data.public.lu and Peppol IDs are unknown; the ISSUE_SOURCE_KEY column says
    which side is at fault. The ``peppol_id`` field may list several
    space-separated IDs, each of which is checked.
    """
    unknown = []
    for row in rows:
        udata_id = row.get(UDATA_ID_KEY)
        if udata_id and udata_id not in udata_ids:
            unknown.append({**row, ISSUE_SOURCE_KEY: UDATA_SOURCE})

        peppol_tokens = row.get(PEPPOL_ID_KEY, "").split()
        if peppol_tokens and any(tok not in peppol_ids for tok in peppol_tokens):
            unknown.append({**row, ISSUE_SOURCE_KEY: PEPPOL_SOURCE})
    return unknown


def name_mismatch_rows(
    rows: list[dict[str, str]],
    udata_names: dict[str, str],
    peppol_names: dict[str, str],
) -> list[dict[str, str]]:
    """Source rows whose name differs from the one reported by its reference API.

    Only rows whose ID is known to the relevant API are considered. The API name
    is appended as an ``api_name`` column and the ISSUE_SOURCE_KEY column tells
    which side the mismatch is on. Peppol names are only compared when the row
    carries a single Peppol ID (a lone name cannot map to several partners).
    """
    mismatches = []
    for row in rows:
        udata_id = row.get(UDATA_ID_KEY)
        if udata_id in udata_names and row.get(UDATA_NAME_KEY, "") != udata_names[udata_id]:
            mismatches.append(
                {**row, "api_name": udata_names[udata_id], ISSUE_SOURCE_KEY: UDATA_SOURCE}
            )

        peppol_tokens = row.get(PEPPOL_ID_KEY, "").split()
        if len(peppol_tokens) == 1 and peppol_tokens[0] in peppol_names:
            api_name = peppol_names[peppol_tokens[0]]
            if row.get(PEPPOL_NAME_KEY, "") != api_name:
                mismatches.append(
                    {**row, "api_name": api_name, ISSUE_SOURCE_KEY: PEPPOL_SOURCE}
                )
    return mismatches


def organizations_without_peppol(
    organizations: list[dict], mapped_ids: set[str]
) -> list[dict[str, str]]:
    """Organizations (with the required badges) whose udata ID is not mapped."""
    missing = []
    for org in organizations:
        if not has_required_badges(org):
            continue
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
        udata_names = {
            org["id"]: (org.get("name") or "").strip()
            for org in organizations
            if org.get("id")
        }
        peppol_names = fetch_peppol_partners()
        all_rows = read_rows(args.csv, apply_filter=False)

        unknown_rows = unknown_id_rows(
            all_rows, set(udata_names), set(peppol_names)
        )
        unknown_path = args.output_dir / f"{UNKNOWN_BASE}.csv"
        write_csv(unknown_rows, unknown_path)
        print(
            f"Found {len(unknown_rows)} source rows with an ID "
            f"missing from its reference API"
        )
        print(f"  -> {unknown_path}")

        mismatch_rows = name_mismatch_rows(all_rows, udata_names, peppol_names)
        mismatch_path = args.output_dir / f"{MISMATCH_BASE}.csv"
        write_csv(mismatch_rows, mismatch_path)
        print(
            f"Found {len(mismatch_rows)} source rows whose name "
            f"differs from its reference API"
        )
        print(f"  -> {mismatch_path}")

        eligible = [org for org in organizations if has_required_badges(org)]
        missing = organizations_without_peppol(organizations, mapped_udata_ids(args.csv))
        missing_path = args.output_dir / f"{MISSING_BASE}.csv"
        write_csv(missing, missing_path)
        print(
            f"Found {len(missing)} of {len(eligible)} organizations "
            f"without a Peppol ID"
        )
        print(f"  -> {missing_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
