"""
Optional, per-developer-machine memory for usage_harvester findings.

Deliberately NOT part of the tool's own repo and NEVER touched by git: it
lives under the developer's home directory, one file per machine. It is not
shared between developers and never leaves the VDI it was written on.

Safety rule this whole module exists to enforce: the SAME type/method name
can have a genuinely DIFFERENT real shape across different apps (a shared
internal library can evolve between migrations, or a name can coincidentally
collide). So a cached shape may only ever *fill a gap* — supply a method this
run's own source never referenced at all — and can never override what this
run actually observed. Fresh, this-app evidence always wins.
"""
import json
from pathlib import Path
from typing import Dict

DEFAULT_PATH = Path.home() / '.migration_tool_cache' / 'unavailable_pkg_shapes.json'


def load(path: Path = DEFAULT_PATH) -> Dict[str, dict]:
    """Best-effort load. Never raises — a missing or corrupt cache file must
    not break a migration run; it just means starting from no memory."""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save(cache: Dict[str, dict], path: Path = DEFAULT_PATH) -> None:
    """Best-effort save. Never raises — a cache write failure (e.g. read-only
    home directory) must not break a migration run."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding='utf-8')
    except Exception:
        pass


def apply_as_fallback(fresh: Dict[str, dict], cache: Dict[str, dict]) -> Dict[str, dict]:
    """Fresh entries are authoritative and returned untouched. For each type
    already present in `fresh` (i.e. this app's own code does use it), any
    cached method NOT found fresh is added and marked {'from_cache': True} so
    the generated stub can flag it as unverified against this app.

    Types absent from `fresh` are never added from cache alone — if nothing
    in this app's own source refers to a type, no stub is needed for it here,
    regardless of what a previous app's migration once found.

    Does not mutate either input."""
    result: Dict[str, dict] = {}
    for full_name, shape in fresh.items():
        methods = dict(shape.get('methods', {}))
        cached_shape = cache.get(full_name, {})
        for key, cached_method in cached_shape.get('methods', {}).items():
            if key not in methods:
                methods[key] = {**cached_method, 'from_cache': True}
        result[full_name] = {**shape, 'methods': methods}
    return result


def merge_fresh_into_cache(cache: Dict[str, dict], fresh: Dict[str, dict]) -> Dict[str, dict]:
    """Fresh findings always overwrite whatever was cached for the same
    (type, method) key — real evidence from an actual app outranks a memory
    of a possibly-since-changed shape. Cache entries untouched by this run
    (other types/methods) are preserved as-is. Does not mutate either input."""
    result: Dict[str, dict] = {k: {'methods': dict(v.get('methods', {}))} for k, v in cache.items()}
    for full_name, shape in fresh.items():
        existing_methods = result.setdefault(full_name, {'methods': {}})['methods']
        for key, method in shape.get('methods', {}).items():
            # strip any from_cache marker before persisting — this key's
            # presence in `fresh` means it was actually observed this run
            existing_methods[key] = {'return_type': method.get('return_type'), 'static': method.get('static', False)}
    return result
