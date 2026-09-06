"""Data-only source closure for the later bounded V4 fixture manifest."""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import stat


__all__ = (
    "FixtureManifestError",
    "build_session_source_closure",
    "build_runtime_catalog",
    "load_runtime_catalog_bytes",
    "build_fixture_runtime_manifest",
    "build_fixture_runtime_manifest_from_catalog",
)

_APP_ROOT = "/app"
_BOOTSTRAP_DESTINATIONS = frozenset((
    "/run/m3-v4/session-config.json",
    "/run/m3-v4/session-config.sha256",
))
_MAX_RUNTIME_CATALOG_BYTES = 1_048_576


class FixtureManifestError(ValueError):
    """The supplied fixture-root source graph is incomplete or ambiguous."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise FixtureManifestError("source closure cannot be canonically encoded") from error


def _relative_destination(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise FixtureManifestError("source path escapes the declared fixture root") from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise FixtureManifestError("source path is not a canonical fixture-relative path")
    return _APP_ROOT + "/" + relative.as_posix()


def _read_regular_source(root: pathlib.Path, path: pathlib.Path) -> tuple[str, bytes, int]:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        metadata = resolved.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise FixtureManifestError("source closure entries must be one-link regular files")
        data = resolved.read_bytes()
    except FixtureManifestError:
        raise
    except OSError as error:
        raise FixtureManifestError("source closure entry cannot be read") from error
    return _relative_destination(root, resolved), data, stat.S_IMODE(metadata.st_mode)


def _resolve_tools_module(root: pathlib.Path, module: str) -> pathlib.Path:
    if not module.startswith("tools.") or module == "tools":
        raise FixtureManifestError("only literal tools dependencies can be resolved")
    parts = module.split(".")[1:]
    if any(not part.isidentifier() for part in parts):
        raise FixtureManifestError("tools dependency name is invalid")
    module_path = root.joinpath("tools", *parts)
    candidates = (module_path.with_suffix(".py"), module_path / "__init__.py")
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    raise FixtureManifestError(f"literal tools dependency {module!r} cannot be resolved")


def _literal_tools_imports(source: bytes, destination: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source, filename=destination)
    except (SyntaxError, ValueError) as error:
        raise FixtureManifestError("source closure entry is not valid Python source") from error

    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name) and target.id == "__import__":
                raise FixtureManifestError("dynamic import is not permitted in a fixture source graph")
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "importlib"
                and target.attr == "import_module"
            ):
                raise FixtureManifestError("dynamic import is not permitted in a fixture source graph")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tools" or alias.name.startswith("tools."):
                    dependencies.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            if module == "tools":
                for alias in node.names:
                    if alias.name == "*":
                        raise FixtureManifestError("star import is not permitted in a fixture source graph")
                    dependencies.add(f"tools.{alias.name}")
            elif module is not None and module.startswith("tools."):
                dependencies.add(module)
    return tuple(sorted(dependencies))


def build_session_source_closure(
    workspace_root: pathlib.Path,
    entry_source: pathlib.Path,
) -> dict[str, object]:
    """Build a deterministic source-only graph from one session entry script.

    The result deliberately covers only the entry source and its literal
    ``tools`` imports.  The Python interpreter, extension, ELF, loader, and
    fixture-data closure remain separate manifest inputs; callers cannot treat
    this source graph alone as a runnable fixture manifest.
    """
    if not isinstance(workspace_root, pathlib.Path) or not isinstance(entry_source, pathlib.Path):
        raise FixtureManifestError("workspace root and entry source must be Path values")
    try:
        root = workspace_root.resolve(strict=True)
        if not root.is_dir():
            raise FixtureManifestError("fixture workspace root must be a directory")
        entry = entry_source.resolve(strict=True)
        entry.relative_to(root)
    except FixtureManifestError:
        raise
    except OSError as error:
        raise FixtureManifestError("fixture source root cannot be resolved") from error

    pending: list[pathlib.Path] = [entry]
    visited: dict[str, tuple[pathlib.Path, bytes, int]] = {}
    edges: set[tuple[str, str]] = set()
    while pending:
        path = pending.pop()
        destination, source, mode = _read_regular_source(root, path)
        if destination in visited:
            continue
        visited[destination] = (path.resolve(strict=True), source, mode)
        for module in _literal_tools_imports(source, destination):
            dependency = _resolve_tools_module(root, module)
            dependency_destination = _relative_destination(root, dependency)
            edges.add((destination, dependency_destination))
            if dependency_destination not in visited:
                pending.append(dependency)

    entries = tuple(
        {
            "destination": destination,
            "byte_size": len(source),
            "mode": mode,
            "sha256": hashlib.sha256(source).hexdigest(),
        }
        for destination, (_path, source, mode) in sorted(visited.items())
    )
    edge_records = tuple(
        {"from": source, "to": target, "kind": "import"}
        for source, target in sorted(edges)
    )
    result: dict[str, object] = {
        "schema": 1,
        "state": "SOURCE_CLOSURE_COMPLETE",
        "root": _relative_destination(root, entry),
        "entries": entries,
        "edges": edge_records,
    }
    result["source_closure_sha256"] = hashlib.sha256(_canonical_bytes(result)).hexdigest()
    return result


def _manifest_destination(value: object) -> str:
    if type(value) is not str or not value.startswith("/") or value == "/":
        raise FixtureManifestError("manifest destination is invalid")
    if "//" in value or value.endswith("/"):
        raise FixtureManifestError("manifest destination is not canonical")
    if any(part in ("", ".", "..") for part in value.split("/")[1:]):
        raise FixtureManifestError("manifest destination is not canonical")
    return value


def _external_manifest_entry(destination: str, source: pathlib.Path, category: str) -> dict[str, object]:
    if not isinstance(source, pathlib.Path):
        raise FixtureManifestError("manifest source must be a Path value")
    try:
        resolved = source.resolve(strict=True)
        metadata = resolved.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise FixtureManifestError("manifest entries must be one-link regular files")
        data = resolved.read_bytes()
    except FixtureManifestError:
        raise
    except OSError as error:
        raise FixtureManifestError("manifest entry cannot be read") from error
    return {
        "destination": destination,
        "source": resolved.as_posix(),
        "category": category,
        "byte_size": len(data),
        "mode": stat.S_IMODE(metadata.st_mode),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _resource_policy(entries: tuple[dict[str, object], ...]) -> dict[str, int]:
    byte_sizes = tuple(entry["byte_size"] for entry in entries)
    if any(type(size) is not int or size < 0 for size in byte_sizes):
        raise FixtureManifestError("manifest entries have invalid byte sizes")
    return {
        "regular_entry_count": len(entries),
        "total_regular_bytes": sum(byte_sizes),
        "largest_regular_entry": max(byte_sizes, default=0),
    }


def build_runtime_catalog(
    runtime_files: dict[str, pathlib.Path],
    *,
    unresolved: tuple[str, ...],
) -> dict[str, object]:
    """Pin observed regular runtime files without claiming a closed runtime.

    The unresolved list is mandatory: a catalog assembled from observed imports
    and ELF dependencies is useful as a future manifest input, but it cannot
    substitute for the startup, native-effect, and virtual-resource closure.
    """
    if type(runtime_files) is not dict:
        raise FixtureManifestError("runtime files must be an exact dictionary")
    if type(unresolved) is not tuple or not unresolved:
        raise FixtureManifestError("runtime catalog must retain unresolved closure reasons")
    if any(type(reason) is not str or not reason or not reason.isascii() for reason in unresolved):
        raise FixtureManifestError("runtime catalog unresolved reason is invalid")
    if tuple(sorted(set(unresolved))) != unresolved:
        raise FixtureManifestError("runtime catalog unresolved reasons must be unique lexical order")

    entries_by_destination: dict[str, dict[str, object]] = {}
    for raw_destination, source in runtime_files.items():
        destination = _manifest_destination(raw_destination)
        if destination in _BOOTSTRAP_DESTINATIONS:
            raise FixtureManifestError("the bootstrap pair is outside the runtime catalog")
        if destination in entries_by_destination:
            raise FixtureManifestError("runtime catalog destination is duplicated")
        entries_by_destination[destination] = _external_manifest_entry(
            destination,
            source,
            "runtime",
        )
    entries = tuple(entries_by_destination[key] for key in sorted(entries_by_destination))
    catalog: dict[str, object] = {
        "schema": 1,
        "state": "OBSERVED_RUNTIME_CATALOG",
        "completeness": "UNRESOLVED",
        "entries": entries,
        "unresolved": unresolved,
        "resource_policy": _resource_policy(entries),
    }
    catalog["runtime_catalog_sha256"] = hashlib.sha256(_canonical_bytes(catalog)).hexdigest()
    return catalog


def load_runtime_catalog_bytes(data: bytes) -> dict[str, object]:
    """Load canonical JSON (optionally one POSIX text-file newline) without I/O."""
    if type(data) is not bytes or not data or len(data) > _MAX_RUNTIME_CATALOG_BYTES:
        raise FixtureManifestError("runtime catalog bytes are invalid")
    canonical_input = data[:-1] if data.endswith(b"\n") else data
    if not canonical_input:
        raise FixtureManifestError("runtime catalog bytes are invalid")
    try:
        parsed = json.loads(canonical_input.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise FixtureManifestError("runtime catalog bytes cannot be decoded") from error
    if type(parsed) is not dict:
        raise FixtureManifestError("runtime catalog root is invalid")
    try:
        canonical = _canonical_bytes(parsed)
    except FixtureManifestError:
        raise FixtureManifestError("runtime catalog bytes are invalid") from None
    if canonical != canonical_input:
        raise FixtureManifestError("runtime catalog bytes are not canonical")
    entries = parsed.get("entries")
    unresolved = parsed.get("unresolved")
    if type(entries) is not list or type(unresolved) is not list:
        raise FixtureManifestError("runtime catalog list fields are invalid")
    loaded = dict(parsed)
    loaded["entries"] = tuple(entries)
    loaded["unresolved"] = tuple(unresolved)
    return loaded


def _runtime_files_from_catalog(catalog: object) -> tuple[dict[str, pathlib.Path], str]:
    if type(catalog) is not dict:
        raise FixtureManifestError("runtime catalog must be an exact dictionary")
    required_keys = {
        "schema",
        "state",
        "completeness",
        "entries",
        "unresolved",
        "resource_policy",
        "runtime_catalog_sha256",
    }
    if set(catalog) != required_keys:
        raise FixtureManifestError("runtime catalog keys are invalid")
    if (
        type(catalog["schema"]) is not int
        or catalog["schema"] != 1
        or catalog["state"] != "OBSERVED_RUNTIME_CATALOG"
    ):
        raise FixtureManifestError("runtime catalog state is invalid")
    if catalog["completeness"] != "UNRESOLVED":
        raise FixtureManifestError("runtime catalog completeness is invalid")
    unresolved = catalog["unresolved"]
    if (
        type(unresolved) is not tuple
        or not unresolved
        or any(type(reason) is not str or not reason or not reason.isascii() for reason in unresolved)
        or tuple(sorted(set(unresolved))) != unresolved
    ):
        raise FixtureManifestError("runtime catalog unresolved reasons are invalid")
    catalog_digest = catalog["runtime_catalog_sha256"]
    if (
        type(catalog_digest) is not str
        or len(catalog_digest) != 64
        or any(character not in "0123456789abcdef" for character in catalog_digest)
    ):
        raise FixtureManifestError("runtime catalog digest is invalid")
    digest_input = dict(catalog)
    digest_input.pop("runtime_catalog_sha256")
    if hashlib.sha256(_canonical_bytes(digest_input)).hexdigest() != catalog_digest:
        raise FixtureManifestError("runtime catalog digest does not match its entries")

    entries = catalog["entries"]
    if type(entries) is not tuple:
        raise FixtureManifestError("runtime catalog entries are invalid")
    files: dict[str, pathlib.Path] = {}
    expected_destinations: list[str] = []
    for entry in entries:
        if type(entry) is not dict or set(entry) != {
            "destination", "source", "category", "byte_size", "mode", "sha256",
        }:
            raise FixtureManifestError("runtime catalog entry is invalid")
        destination = _manifest_destination(entry["destination"])
        source_text = entry["source"]
        if type(source_text) is not str or not source_text.startswith("/"):
            raise FixtureManifestError("runtime catalog source is invalid")
        if entry["category"] != "runtime":
            raise FixtureManifestError("runtime catalog entry category is invalid")
        if (
            type(entry["byte_size"]) is not int
            or entry["byte_size"] < 0
            or type(entry["mode"]) is not int
            or not 0 <= entry["mode"] <= 0o7777
            or type(entry["sha256"]) is not str
            or len(entry["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in entry["sha256"])
        ):
            raise FixtureManifestError("runtime catalog entry facts are invalid")
        current = _external_manifest_entry(destination, pathlib.Path(source_text), "runtime")
        if current != entry:
            raise FixtureManifestError("runtime catalog source no longer matches its pinned identity")
        if destination in files:
            raise FixtureManifestError("runtime catalog destination is duplicated")
        files[destination] = pathlib.Path(source_text)
        expected_destinations.append(destination)
    if expected_destinations != sorted(expected_destinations):
        raise FixtureManifestError("runtime catalog entries are not lexical")
    policy = catalog["resource_policy"]
    if type(policy) is not dict or set(policy) != {
        "regular_entry_count", "total_regular_bytes", "largest_regular_entry",
    } or any(type(value) is not int or value < 0 for value in policy.values()):
        raise FixtureManifestError("runtime catalog resource policy is invalid")
    expected_policy = _resource_policy(entries)
    if policy != expected_policy:
        raise FixtureManifestError("runtime catalog resource policy does not match entries")
    return files, catalog_digest


def build_fixture_runtime_manifest(
    workspace_root: pathlib.Path,
    entry_source: pathlib.Path,
    runtime_files: dict[str, pathlib.Path],
    fixture_files: dict[str, pathlib.Path],
) -> dict[str, object]:
    """Seal declared runtime and fixture files around the source closure.

    The bootstrap config and digest pair are intentionally excluded because the
    session configuration carries the manifest digest.  They are pinned by the
    fixed sidecar bootstrap protocol instead, avoiding a circular digest.
    This remains a declared manifest: callers must separately establish that
    the runtime-file inventory is a complete interpreter and ELF closure.
    """
    if type(runtime_files) is not dict or type(fixture_files) is not dict:
        raise FixtureManifestError("runtime and fixture files must be exact dictionaries")
    source_closure = build_session_source_closure(workspace_root, entry_source)
    try:
        root = workspace_root.resolve(strict=True)
    except OSError as error:
        raise FixtureManifestError("fixture workspace root cannot be resolved") from error
    entries_by_destination: dict[str, dict[str, object]] = {}
    source_entries = source_closure["entries"]
    if type(source_entries) is not tuple:
        raise FixtureManifestError("source closure entries are invalid")
    for source_entry in source_entries:
        if type(source_entry) is not dict:
            raise FixtureManifestError("source closure entry is invalid")
        destination = source_entry.get("destination")
        if type(destination) is not str or not destination.startswith(_APP_ROOT + "/"):
            raise FixtureManifestError("source closure entry is invalid")
        relative = pathlib.PurePosixPath(destination.removeprefix(_APP_ROOT + "/"))
        source = root.joinpath(*relative.parts)
        entries_by_destination[destination] = _external_manifest_entry(
            destination,
            source,
            "session_source",
        )
    for category, mapping in (("runtime", runtime_files), ("fixture", fixture_files)):
        for raw_destination, source in mapping.items():
            destination = _manifest_destination(raw_destination)
            if destination in _BOOTSTRAP_DESTINATIONS:
                raise FixtureManifestError("the bootstrap pair is outside the fixture manifest")
            if destination in entries_by_destination:
                raise FixtureManifestError("manifest destination is duplicated")
            entries_by_destination[destination] = _external_manifest_entry(
                destination,
                source,
                category,
            )
    entries = tuple(entries_by_destination[key] for key in sorted(entries_by_destination))
    manifest: dict[str, object] = {
        "schema": 1,
        "state": "DECLARED_RUNTIME_MANIFEST",
        "entrypoint": source_closure["root"],
        "source_closure_sha256": source_closure["source_closure_sha256"],
        "entries": entries,
        "resource_policy": _resource_policy(entries),
    }
    manifest["fixture_manifest_sha256"] = hashlib.sha256(_canonical_bytes(manifest)).hexdigest()
    return manifest


def build_fixture_runtime_manifest_from_catalog(
    workspace_root: pathlib.Path,
    entry_source: pathlib.Path,
    runtime_catalog: dict[str, object],
    fixture_files: dict[str, pathlib.Path],
) -> dict[str, object]:
    """Recheck a pinned unresolved runtime catalog before manifest assembly."""
    runtime_files, catalog_digest = _runtime_files_from_catalog(runtime_catalog)
    manifest = build_fixture_runtime_manifest(
        workspace_root,
        entry_source,
        runtime_files,
        fixture_files,
    )
    manifest["runtime_catalog_sha256"] = catalog_digest
    manifest_digest_input = dict(manifest)
    manifest_digest_input.pop("fixture_manifest_sha256")
    manifest["fixture_manifest_sha256"] = hashlib.sha256(
        _canonical_bytes(manifest_digest_input)
    ).hexdigest()
    return manifest
