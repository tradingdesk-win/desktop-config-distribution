import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml


IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
SENSITIVE = re.compile(r"^(?:authorization|proxy[-_]authorization|cookie|set[-_]cookie|(?:x[-_])?api[-_]?key|(?:access[-_]|refresh[-_]|x[-_])?token|client[-_]secret|secret[-_]key|password)$", re.I)
PLACEHOLDER = re.compile(r"(?:Bearer )?\$\{[A-Z_][A-Z0-9_]*\}")
SECRET = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}")
SOURCES = {"import": "template.json", "market": "config.yaml"}
EXCLUDED_SOURCES = {"market/providers/xuangubao/config.yaml"}
EXCLUDED_IDS = {"xuangubao"}


def unique_mapping(pairs):
    mapping = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError(f"duplicate key: {key}")
        mapping[key] = value
    return mapping


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return unique_mapping(self.construct_pairs(node, deep=deep))


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def text(value):
    if not isinstance(value, str) or not value or len(value.encode()) > 160 or value.strip() != value or any(char in value for char in "\r\n\t\0"):
        raise ValueError("missing or invalid display text or version")
    return value


def markets_for(values, chart=False):
    if not isinstance(values, list) or not 1 <= len(values) <= 16:
        raise ValueError("missing or invalid market list")
    result = set()
    for value in values:
        value = text(value).upper()
        value = {"A_STOCK": "CN", "CN_A_STOCK": "CN"}.get(value, value)
        if chart and value in ("CN_STOCK", "HK_STOCK", "US_STOCK"):
            value = value.removesuffix("_STOCK")
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("invalid market identifier")
        result.add(value)
    return sorted(result)


def check_request(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if SENSITIVE.fullmatch(str(key)) and child not in (None, "") and not (isinstance(child, str) and PLACEHOLDER.fullmatch(child)):
                raise ValueError("literal credential in request configuration")
            check_request(child)
    elif isinstance(value, list):
        for child in value:
            check_request(child)
    elif isinstance(value, str) and value.startswith(("https://", "http://", "wss://", "ws://", "//")):
        address = urlsplit(value)
        if address.username is not None:
            raise ValueError("embedded credentials in URL")
        for pair in address.query.split("&"):
            key, _, item = pair.partition("=")
            if SENSITIVE.fullmatch(key) and item and not PLACEHOLDER.fullmatch(item):
                raise ValueError("literal credential in URL")


def load_source(path, kind):
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1 << 20:
        raise ValueError("invalid configuration file")
    data = path.read_bytes()
    if SECRET.search(data):
        raise ValueError("potential hardcoded credential")
    if kind == "import":
        exported = json.loads(data, object_pairs_hook=unique_mapping)
        config = exported["template"]
        identifier = config["template_id"]
        version = config.get("source_version") or exported["version"]
        markets = markets_for(config["supported_markets"])
        capabilities = ["template"]
    else:
        config = yaml.load(data, Loader=UniqueLoader)
        identifier = config["id"]
        version = config["version"]
        values = list(config["supported_markets"])
        api = config.get("api") or {}
        directory = config.get("symbol_directory")
        daily_sections = [config.get("market_daily"), config.get("index_daily")]
        for section in [api, directory, *daily_sections]:
            if section is not None:
                check_request(section)
        for section in [directory, *daily_sections]:
            if section and section.get("market"):
                values.append(section["market"])
        markets = markets_for(values, chart=True)
        capabilities = []
        if not directory or any(daily_sections) or any((api.get(key) or {}).get("endpoint") for key in ("kline", "trend", "realtime", "batch_realtime")) or api.get("kline_stream") or (api.get("kline") or {}).get("unadjusted"):
            capabilities.append("market_data")
        if directory:
            capabilities.append("stock_directory")
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise ValueError("invalid provider ID")
    name = text(config["name"])
    item = {"id": identifier, "name": name, "version": text(version), "markets": markets, "capabilities": capabilities, "file": f"{kind}-{identifier}{'.json' if kind == 'import' else '.yaml'}", "sha256": sha256(data)}
    if kind == "import":
        item["broker"] = name
    return item, data


def read_sources(roots):
    entries = {}
    for kind, filename in SOURCES.items():
        root = roots[kind]
        directory = root / "providers"
        if directory.is_symlink():
            raise ValueError(f"{kind}/providers must be a directory")
        paths = sorted(directory.glob(f"*/{filename}"))
        if not paths:
            raise ValueError(f"no {kind} providers found")
        for path in paths:
            source = f"{kind}/{path.relative_to(root).as_posix()}"
            if source.casefold() in EXCLUDED_SOURCES:
                continue
            try:
                item, data = load_source(path, kind)
            except (ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as error:
                raise ValueError(f"{source}: invalid or unsafe configuration ({type(error).__name__})") from None
            if item["id"].casefold() not in EXCLUDED_IDS:
                entries[source] = item, data
    return entries


def build_release(entries):
    catalog, files = {}, {}
    for source, (item, data) in entries.items():
        key = item["id"].casefold()
        if key in catalog:
            raise ValueError(f"{source}: duplicate provider ID")
        catalog[key] = item
        files[item["file"]] = data
    items = [catalog[key] for key in sorted(catalog)]
    manifest = {"schema": 1, "release": f"providers-{sha256(json_bytes(items))[:16]}", "min_protocol": 1, "max_protocol": 1, "items": items}
    files["manifest.json"] = json_bytes(manifest)
    if len(items) > 100 or len(files["manifest.json"]) > 128 << 10:
        raise ValueError("catalog exceeds the desktop protocol limit")
    return files, len(items)


def preserve_pending(release, entries, pending):
    previous = json.loads((release / "manifest.json").read_bytes())
    by_digest = {item["sha256"]: item for item in previous["items"]}
    remaining = {}
    for source, digest in pending.items():
        if source.casefold() in EXCLUDED_SOURCES:
            continue
        if source in entries and entries[source][0]["sha256"] == digest:
            continue
        item = by_digest[digest]
        if item["id"].casefold() in EXCLUDED_IDS:
            continue
        path = release / item["file"]
        data = path.read_bytes()
        if sha256(data) != digest:
            raise ValueError(f"{source}: stored local snapshot does not match recorded digest")
        entries[source] = item, data
        remaining[source] = digest
    if remaining:
        print(f"Kept {len(remaining)} local configurations while upstream catches up.")
    return remaining


def sync(root, roots, upstream):
    entries = read_sources(roots)
    handoff = root / "upstream-pending.json"
    release = root / "v1"
    if upstream:
        pending = preserve_pending(release, entries, json.loads(handoff.read_bytes())) if handoff.exists() else {}
    else:
        pending = {source: item["sha256"] for source, (item, _) in entries.items()}
    files, count = build_release(entries)
    license_file = roots["market"] / "LICENSE"
    if license_file.is_symlink() or not license_file.is_file():
        raise ValueError("missing market-provider license")
    license_text = license_file.read_bytes()
    if not license_text or len(license_text) > 65536 or SECRET.search(license_text):
        raise ValueError("invalid market-provider license")
    release.mkdir(exist_ok=True)
    for previous in release.iterdir():
        if previous.is_symlink() or not previous.is_file() or not re.fullmatch(r"manifest\.json|(?:import|market)-[A-Za-z0-9_-]+\.(?:json|yaml)", previous.name):
            raise ValueError("unexpected file in generated release directory")
    for name, data in files.items():
        (release / name).write_bytes(data)
    for previous in release.iterdir():
        if previous.name not in files:
            previous.unlink()
    (root / "MARKET-PROVIDERS-LICENSE.txt").write_bytes(license_text)
    if pending:
        handoff.write_bytes(json_bytes(pending))
    else:
        handoff.unlink(missing_ok=True)
    print(f"Generated {count} configurations; manifest SHA-256: {sha256(files['manifest.json'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-repo", required=True, type=Path)
    parser.add_argument("--market-repo", required=True, type=Path)
    parser.add_argument("--upstream", action="store_true")
    args = parser.parse_args()
    sync(Path(__file__).resolve().parents[1], {"import": args.import_repo, "market": args.market_repo}, args.upstream)


if __name__ == "__main__":
    main()
