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
  --base-package "com.example.myapp" \
  --group-id "com.example.myapp" \
  --artifact-id "my-app" \
  --persistence hana-cloud \
  --unavailable-packages "com.example.myapp.internal" \
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

`com.sap.security.api.*` imports are **not** commented out (unlike `com.sap.engine.*` and `com.sap.conn.jco.*`). Instead, `StubGenerator` writes ten compilable Java stub files into the output project (nine under `com/sap/security/api/`: `IUser`, `IPrincipal`, `IUserFactory`, `IRoleFactory`, `IGroup`, `IGroupFactory`, `IAuthenticator`, `UMException`, `UMFactory`; one under `com/sap/engine/...`: `ApplicationPropertiesChangeListener`). This keeps those imports resolving at compile time; the stubs throw `UnsupportedOperationException` at runtime. The `import_transformer.py` has an explicit note about this — do not move `com.sap.security.*` into `SAP_IMPORTS_REMOVE_WITH_TODO`.

`UMFactory`'s method set (`getAuthenticatedUser`, `getUserFactory`, `getRoleFactory`, `getGroupFactory`, `getAuthenticator`) is **best-effort, not exhaustive** — it covers every `UMFactory.*` call seen across real migrations so far. A real compile run is what surfaces the next missing one (`cannot find symbol: method ...` on `UMFactory`) — when that happens, add the missing method/stub type rather than commenting out the caller's import, to stay consistent with this pattern.

### Why some imports are commented out but "cannot find symbol" errors still remain

Commenting out an import (`SAP_IMPORTS_REMOVE_WITH_TODO`, `JAVA_EE_CONTAINER_IMPORTS_REMOVE_WITH_TODO`, `unavailable_packages`) only prevents "package does not exist" at that one line. It does **not** touch the rest of the file — if the same type is used as a field type, method parameter/return type, annotation argument, or inside a method body, that usage still fails to compile, now as "cannot find symbol" instead. This is deliberate, not a bug: safely rewriting a usage (as opposed to a self-contained import line) requires knowing the surrounding Java structure — you can't blank out a method's return type without removing the whole method, and removing a method can break its callers elsewhere in the file or in other files. That's whole-program, AST-level analysis (see `java_parser.py` below), which the regex-based transformer chain deliberately doesn't attempt.

Categories that get this "comment the import, usage remains manual" treatment: `com.sap.bpm.*` (BPM workflow — being replaced by BTP Build Process Automation), `com.sap.scheduler.*` (MDB/Job Scheduler), `javax.resource.cci.*` (JCA connector), leftover `javax.ejb.*`/`javax.interceptor.*`/`org.springframework.ejb.*` (EJB-container plumbing the `@EJB`→`@Autowired` swap doesn't convert), and `javax.jws.*` (JAX-WS, removed from the JDK). If a future migration needs these usages actually resolved rather than just flagged, see the "usage-aware rewriting" discussion — the current answer (as of this tool's design) is to extend `StubGenerator` with compilable stubs for the specific types/methods actually called, not to attempt usage-commenting.

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

`parsers/dtdbtable_parser.py` parses SAP NWDS MetaDataAPI-generated `.dtdbtable` XML files (individually or from a ZIP). `HdiGenerator` consumes the parsed table dicts and renders `.hdbtable` CDS files.

The real schema (verified against actual exports — an earlier version of this parser assumed a different, XMI-wrapped `<dictionary:DBTable>` schema that no real export actually uses, and silently returned zero tables for every file with no error surfaced): the root element **is** the table itself — `<DtDbTable xmlns="http://xml.sap.com/2002/10/metamodel/dictionary" name="...">` — not a nested child. Columns are `<DtField>` elements under `<DtStructure.StructureElements>`, with `builtInType`/`length`/`notNull` attributes. Primary key columns are declared **separately**, under `<DtDbTable.PrimaryKey><DtPrimaryKey.KeyElements>`, via `<Core.Reference path="StructureElement:COL_NAME"/>` — key membership is not a per-column attribute. Tables with no `KeyElements` at all get a heuristically-assigned PK with a `-- NOTE:` comment in the output file — these must be reviewed before deploying.

## Key conventions

- **No client-specific strings anywhere in this tool.** The tool is generic. Do not add package patterns, stub classes, or example values that reference any specific organisation or project. Generic examples use `com.example.myapp` / `my-service`.
- `SCAFFOLD_PACKAGE_FRAGMENTS` must stay `[]` by default — it is an opt-in configuration, not a hardcoded filter. `MigrationConfig.unavailable_packages` (populated via `--unavailable-packages`) follows the same pattern for a *specific* codebase's own internal/proprietary import prefixes (e.g. a client's own utility packages) — empty by default, comment-out-with-TODO only when the caller supplies it per-run. Never hardcode a real client's package prefix into `import_transformer.py` itself; that's exactly what this flag exists to avoid.
- `--base-package` exists because `_detect_base_package`'s common-prefix heuristic breaks down on a source tree spanning more than one top-level package (e.g. `com.truist.*` and `com.bbt.*` in the same codebase) — the common prefix collapses to something too shallow (e.g. just `com`), which silently produces a second, wrong `@SpringBootApplication` class when `AppClassGenerator` writes to that shallow package. This has actually happened on a real migration. In `--non-interactive` mode there is no prompt to catch it, so pass `--base-package` explicitly whenever the source isn't a single coherent package tree.
- All new transformers must be stateless and follow the `(source, file_path, scan_result) → (source, todos)` contract. Add them to the transformer list in `migrate.py`.
- Regex-based transformers need care with **anchoring**: a pattern meant to match a declaration (e.g. `class Foo {`) must anchor to the actual start of a line (`^`, `re.MULTILINE`), or it will also match the same words appearing in a comment ("...implementation class for: FooJob") and then greedily consume up to some unrelated `{`. Similarly, keep `\s*` *inside* an optional group (`(?:\s*\(...)?`) rather than immediately before it — otherwise it swallows the separating whitespace even when the optional part doesn't match, gluing a replacement onto the next token (`@EJB\n\tprivate` → `@Autowiredprivate`). Both of these were real bugs found via real compile failures, not hypothetical.
- Tests use pytest `tmp_path` fixtures for full isolation — no test should touch real filesystem paths outside `tmp_path`.
- The test suite has **85 tests** currently. Removing or adding transformer/generator functionality must be reflected in the tests.
