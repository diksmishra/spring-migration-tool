# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Install dependencies (run from migration-tool/)
pip install -r requirements.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_import_transformer.py -v

# Run a single test by name
pytest tests/test_stub_generator.py::test_umfactory_stub_throws_uoe -v

# Run with coverage
pytest --cov=migration_tool --cov-report=term-missing

# Run the tool (interactive)
python migrate.py "C:\path\to\legacy-java-project"

# Run the tool (non-interactive, all options provided)
python migrate.py "C:\path\to\legacy-java-project" \
  --output "C:\path\to\output" \
  --group-id "com.example.myapp" \
  --artifact-id "my-app" \
  --persistence hana-cloud \
  --non-interactive
```

## Architecture

The tool follows a linear pipeline: **scan → configure → transform → generate → report**.

```
migrate.py  (Click CLI + orchestration)
  │
  ├── ProjectScanner.scan()           → scan_result dict
  ├── MigrationConfig(...)            ← shared state passed to everything
  │
  ├── [Transformer chain — applied to every .java file in order]
  │    LoggingTransformer.transform()
  │    ImportTransformer.transform()
  │    PersistenceTransformer.transform()
  │    UtilsTransformer.transform()
  │
  ├── [Generator chain — produce scaffold files once]
  │    PomGenerator / AppClassGenerator / PropertiesGenerator
  │    ManifestGenerator / HdiGenerator / StubGenerator
  │    OpenRewriteGenerator
  │
  └── Reporter.write()                → migration-report.md
```

### Transformer contract

Every transformer is **stateless** and implements the same signature:

```python
def transform(self, source: str, file_path: Path, scan_result: dict) -> Tuple[str, List[str]]:
```

The returned `List[str]` is a list of TODO strings that are passed directly to `Reporter.record_file()`. These become bullets in `migration-report.md` and have a **1:1 relationship** with `// TODO MANUAL` comments inserted into the source. Never add a TODO string without also inserting a `// TODO MANUAL` comment (or vice versa) — breaking this breaks the report.

### Why SAP security imports are treated differently

`com.sap.security.api.*` imports are **not** commented out (unlike `com.sap.engine.*` and `com.sap.conn.jco.*`). Instead, `StubGenerator` writes six compilable Java stub files into the output project under `com/sap/security/api/`. This keeps those imports resolving at compile time; the stubs throw `UnsupportedOperationException` at runtime. The `import_transformer.py` has an explicit note about this — do not move `com.sap.security.*` into `SAP_IMPORTS_REMOVE_WITH_TODO`.

### Why OpenRewrite runs later, not during migration

`OpenRewriteGenerator` only emits `run-openrewrite.sh` — it never invokes Maven/OpenRewrite itself during migration. OpenRewrite's Maven plugin needs to download recipe artifacts from Maven Central, but `migrate.py` is designed to run in air-gapped environments with no repository access. The script is meant to be run later, in a connected environment (e.g. a cloud IDE), where `mvn` can resolve `org.openrewrite.maven:rewrite-maven-plugin` normally — the same way it resolves Spring Boot itself. Do not wire OpenRewrite execution into the migration pipeline itself; keep it as a standalone script the user runs downstream.

### File placement logic

Output file paths are derived from each file's own `package` declaration, not from its source path. This handles legacy projects stored in flat dot-named folders (`dao.impl/`, `service.impl/`) correctly. Test files (detected by `/test/` in path or `Test.java`/`IT.java` suffix) route to `src/test/java/`; all others go to `src/main/java/`.

### Templates

Jinja2 templates live in `templates/`. Generators load them via `jinja2.Environment(loader=FileSystemLoader(...))`. The template directory is resolved relative to `migrate.py`, not the generator files — pass the correct base path when constructing the environment in any new generator.

### `SCAFFOLD_PACKAGE_FRAGMENTS` in scanner.py

This list (`[]` by default) is checked against each file's `package` declaration. Files whose package contains any listed fragment are classified as scaffold (not legacy code) and skipped. If a source tree contains a mix of legacy and Spring Boot scaffold files, add the scaffold package fragment here.

### `java_parser.py` vs regex scanning

`analyzer/java_parser.py` wraps `javalang` for structured AST parsing with regex fallback. It is **not** called by the main pipeline (`scanner.py` does its own regex-based classification). It exists as a utility for future richer analysis. `javalang` gracefully degrades — the tool works without it installed.

### HDI pipeline

`parsers/dtdbtable_parser.py` parses SAP NWDS `.dtdbtable` XMI/XML files (individually or from a ZIP). `HdiGenerator` consumes the parsed table dicts and renders `.hdbtable` CDS files. Tables with no primary key defined in the source get a heuristically-assigned PK with a `-- NOTE:` comment in the output file — these must be reviewed before deploying.

## Key conventions

- **No client-specific strings anywhere in this tool.** The tool is generic. Do not add package patterns, stub classes, or example values that reference any specific organisation or project. Generic examples use `com.example.myapp` / `my-service`.
- `SCAFFOLD_PACKAGE_FRAGMENTS` must stay `[]` by default — it is an opt-in configuration, not a hardcoded filter.
- All new transformers must be stateless and follow the `(source, file_path, scan_result) → (source, todos)` contract. Add them to the transformer list in `migrate.py`.
- Tests use pytest `tmp_path` fixtures for full isolation — no test should touch real filesystem paths outside `tmp_path`.
- The test suite has **47 tests** currently. Removing or adding transformer/generator functionality must be reflected in the tests.
