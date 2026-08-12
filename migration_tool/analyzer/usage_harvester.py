"""
Harvests how an unavailable type is actually used within a single file, so
StubGenerator can synthesize a compilable stand-in automatically instead of
someone hand-writing one after reading a real compile error.

Scope: --unavailable-packages only (a specific codebase's own internal
packages, supplied fresh per run) — not the built-in SAP/EJB comment-out
categories. See CLAUDE.md for why.

Nothing here persists between runs, files, or projects. Everything returned
is discarded the moment the current migration run ends.
"""
import re
from typing import Dict, List, Optional

try:
    import javalang
    _JAVALANG_AVAILABLE = True
except ImportError:
    _JAVALANG_AVAILABLE = False

IMPORT_LINE_PATTERN = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)\s*;', re.MULTILINE)


def unavailable_import_targets(source: str, prefixes: List[str]) -> Dict[str, str]:
    """Return {simple_name: full_dotted_name} for every non-wildcard import in
    `source` that starts with one of `prefixes`. Wildcard imports (`x.y.*`) are
    skipped — there is no specific simple name to harvest or stub for those."""
    targets = {}
    if not prefixes:
        return targets
    for match in IMPORT_LINE_PATTERN.finditer(source):
        full_name = match.group(1)
        if full_name.endswith('.*'):
            continue
        if any(full_name.startswith(p) for p in prefixes):
            simple_name = full_name.rsplit('.', 1)[-1]
            targets[simple_name] = full_name
    return targets


def _type_to_str(t) -> Optional[str]:
    """Reconstruct a printable type name from a javalang type node, walking
    the .sub_type chain (java.util.List<X> parses as three nested
    ReferenceType nodes, not one) to find the real simple name and generics."""
    if t is None:
        return None
    if isinstance(t, javalang.tree.BasicType):
        return t.name + '[]' * len(t.dimensions or [])

    cur = t
    while cur.sub_type is not None:
        cur = cur.sub_type
    simple = cur.name

    generics = ''
    if getattr(cur, 'arguments', None):
        def _arg_str(ta):
            if ta.type is None:
                return '?'
            prefix = {'extends': '? extends ', 'super': '? super '}.get(ta.pattern_type, '')
            return prefix + (_type_to_str(ta.type) or '?')
        generics = '<' + ', '.join(_arg_str(a) for a in cur.arguments) + '>'

    dims = '[]' * len(cur.dimensions or [])
    return simple + generics + dims


def _type_simple_name(t) -> Optional[str]:
    if t is None:
        return None
    if isinstance(t, javalang.tree.BasicType):
        return t.name
    cur = t
    while cur.sub_type is not None:
        cur = cur.sub_type
    return cur.name


def harvest(source: str, type_names: Dict[str, str]) -> Dict[str, dict]:
    """type_names: {simple_name: full_dotted_name} — imports already known to
    be unavailable. Returns, per full_dotted_name actually used in this file:
        {'methods': {"methodName#argCount": {'return_type': str|None, 'static': bool}}}
    Types ever used with `extends` are omitted entirely (an interface-shaped
    stub can't be extended) — callers should fall back to today's comment-out
    behavior for those. Gracefully returns {} if javalang isn't installed or
    parsing fails — same pattern as analyzer/java_parser.py."""
    if not _JAVALANG_AVAILABLE or not type_names:
        return {}

    try:
        tree = javalang.parse.parse(source)
    except Exception:
        return {}

    target_simple_names = set(type_names.keys())

    # Types ever used as an `extends` target must be excluded — can't stub
    # those as an interface.
    excluded = set()
    for _, node in tree.filter(javalang.tree.ClassDeclaration):
        ext = getattr(node, 'extends', None)
        if ext is not None:
            ext_name = _type_simple_name(ext)
            if ext_name in target_simple_names:
                excluded.add(ext_name)

    # variable/field/param name -> declared type simple name, for our targets only
    var_types: Dict[str, str] = {}
    for node_type in (javalang.tree.LocalVariableDeclaration,
                      javalang.tree.FieldDeclaration,
                      javalang.tree.FormalParameter):
        for _, node in tree.filter(node_type):
            type_name = _type_simple_name(node.type)
            if type_name not in target_simple_names:
                continue
            if node_type is javalang.tree.FormalParameter:
                if node.name:
                    var_types[node.name] = type_name
            else:
                for decl in node.declarators:
                    var_types[decl.name] = type_name

    # Direct-initializer return-type inference: declared_type = return type of
    # a non-chained MethodInvocation used as this declaration's initializer.
    inferred_return: Dict[tuple, str] = {}  # (type_name, method_name) -> type str
    for _, node in tree.filter(javalang.tree.LocalVariableDeclaration):
        for decl in node.declarators:
            init = decl.initializer
            if (isinstance(init, javalang.tree.MethodInvocation)
                    and not init.selectors
                    and init.qualifier):
                recv_type = var_types.get(init.qualifier) or (
                    init.qualifier if init.qualifier in target_simple_names else None
                )
                if recv_type:
                    inferred_return[(recv_type, init.member)] = _type_to_str(node.type)

    results: Dict[str, dict] = {}
    for _, node in tree.filter(javalang.tree.MethodInvocation):
        qualifier = node.qualifier
        if not qualifier:
            continue  # implicit-this or chained/cast call — known v1 gap, not guessed at

        is_static = qualifier in target_simple_names
        recv_type = qualifier if is_static else var_types.get(qualifier)
        if not recv_type or recv_type in excluded:
            continue

        full_name = type_names.get(recv_type)
        if not full_name:
            continue

        arg_count = len(node.arguments or [])
        key = f"{node.member}#{arg_count}"
        return_type = inferred_return.get((recv_type, node.member))

        entry = results.setdefault(full_name, {'methods': {}})
        existing = entry['methods'].get(key)
        if existing is None:
            entry['methods'][key] = {'return_type': return_type, 'static': is_static}
        else:
            # keep a known return type over a later None; static-ness only
            # ever strengthens (a method seen both ways stays available both ways)
            if existing['return_type'] is None and return_type is not None:
                existing['return_type'] = return_type
            existing['static'] = existing['static'] or is_static

    return results
