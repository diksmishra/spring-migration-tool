# SAP NetWeaver → Spring Boot Migration Tool

A local Python CLI that converts SAP NetWeaver Java AS projects to Spring Boot, with optional SAP HANA Cloud HDI artifact generation for BTP CF deployments.

---

## Migration overview

These are the end-to-end steps from legacy source code to a running Spring Boot app on BTP CF.

```
Step 1 — Gather source files
        Collect the legacy Java project folder and, if tables need to be
        migrated to HANA Cloud, a ZIP of the exported .dtdbtable files.

Step 2 — Run the migration tool
        python migrate.py "C:\path\to\legacy-java-project"
        Answer the prompts (package, artifact ID, persistence mode, etc.).

Step 3 — Review the generated output
        The tool creates a <artifact-id>-springboot/ folder containing the
        transformed Java sources, pom.xml, manifest.yml, mta.yaml, HDI
        artifacts, and migration-report.md listing items needing manual work.

Step 4 — Zip the generated folder
        Compress <artifact-id>-springboot/ into a .zip archive so it can
        be imported into SAP Business Application Studio (BAS).

Step 5 — Import into BAS
        In BAS: File → Import Project → select the .zip.
        The project opens as a standard Maven workspace.

Step 6 — Deploy to BTP CF
        Open a BAS terminal, navigate to the project root, then run:
        npm run deploy
        This chains: mvn clean package → mbt build → cf deploy (MTA).
        The HDI module deploys first (creates tables), then the Java app.
```

---

## What it does

1. **Scans** your legacy project and classifies all Java files — controllers, services, DAOs, models, enums (`co/`), utils, test files, and EJB-style implementations. Files whose package indicates an existing Spring Boot scaffold (not legacy code) are identified and skipped.
2. **Detects** SAP-specific and removed-platform-API patterns: `com.sap.tc.logging`, `javax.persistence`, JNDI lookups, SAP JCo, SAP UME Security, SAP NetWeaver platform APIs (`com.sap.engine.*`), SAP BPM workflow APIs (`com.sap.bpm.*`), SAP Job Scheduler/MDB APIs (`com.sap.scheduler.*`), JCA connector APIs (`javax.resource.cci.*`), EJB-container plumbing (`javax.ejb.*`, `javax.interceptor.*`, `org.springframework.ejb.*`), and JAX-WS (`javax.jws.*`). Also detects removed/deprecated Java 9–17 APIs (JAXB, `sun.*`, `SecurityManager`, deprecated `Thread` methods, boxed constructors, `finalize()`).
3. **Transforms** every `.java` file:
   - Replaces `SimpleLogger` / `Location` with SLF4J (`Logger` / `LoggerFactory`) — also removes any pre-existing, now-conflicting `Logger` import (e.g. `java.util.logging.Logger`), since Java can't import two different types with the same simple name
   - Rewrites `javax.*` → `jakarta.*` (required for Spring Boot 3.x / Jakarta EE 9+) — persistence, transaction, validation, servlet, and annotation (`@PostConstruct`/`@Resource`/etc.) packages
   - Converts EJB annotations: `@Stateless` / `@Stateful` → `@Service`, `@EJB` → `@Autowired`
   - Removes OpenJPA-specific imports
   - **Comments out** imports that have no classpath equivalent on BTP CF/Spring Boot — `com.sap.engine.*`, `com.sap.conn.jco.*`, `com.sap.bpm.*`, `com.sap.scheduler.*`, `javax.resource.cci.*`, leftover `javax.ejb.*`/`javax.interceptor.*`/`org.springframework.ejb.*`, and `javax.jws.*` (`com.sap.security.*` is the one exception — see below). Leaving these as live `import` statements causes compile failures; each commented-out line gets a `// TODO MANUAL` marker and a 1:1 entry in `migration-report.md`. **Note:** this only fixes the import line itself — if the same type is used as a field, parameter, return type, or inside a method body, that usage still needs manual fixing (see [Limitations](#limitations))
   - **Comments out** any additional import prefixes you supply via `--unavailable-packages` — for a specific codebase's own internal/proprietary packages, without hardcoding any client-specific strings into the tool itself
4. **Places output files** using each file's own `package` declaration, so flat legacy projects (no `src/main/java/` tree) land in the correct nested directory. Test files (path contains `/test/` or name ends in `Test.java` / `Tests.java` / `IT.java`) are routed to `src/test/java/`.
5. **Generates** Spring Boot scaffold files (`pom.xml` with Lombok, main class, properties, `manifest.yml`, `mta.yaml`, root `package.json`).
6. **Generates** HANA Cloud HDI artifacts (`*.hdbtable`, `.hdiconfig`, `.hdinamespace`) from `.dtdbtable` ZIP exports.
7. **Copies** non-Java resources (XML, properties, YAML, JSON) into the output tree, skipping any resources that belong to a pre-existing Spring Boot scaffold.
8. **Generates** `run-openrewrite.sh` — a script that applies further modernization via [OpenRewrite](https://docs.openrewrite.org/) (Java version upgrade, Jakarta EE migration, Spring Boot version upgrade, Log4j→SLF4J logging migration, static-analysis cleanup). Not run during migration itself — see [Automated modernization (OpenRewrite)](#automated-modernization-openrewrite) below.
9. **Writes** `migration-report.md` with one entry per `// TODO MANUAL` comment inserted into source, output-relative file paths, and a summary section for each pattern family (SAP security, SAP platform API, JNDI, JCo).

---

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.9 + | `python --version` |
| pip | bundled with Python | `pip --version` |
| Node.js _(hana-cloud only)_ | 18 + | `node --version` |
| MBT _(hana-cloud only)_ | 1.2 + | `mbt --version` — install with `npm install -g mbt` |
| CF CLI _(hana-cloud only)_ | 8 + | `cf --version` |
| CF multiapps plugin _(hana-cloud only)_ | any | `cf plugins` — install with `cf install-plugin multiapps` |

---

## Installation

```powershell
# 1. Navigate to the tool folder
cd "migration-tool"

# 2. Install dependencies
pip install -r requirements.txt
```

That is all that is required. The tool can then be run directly with `python migrate.py`.

### Optional: virtual environment

If you want to keep the tool's dependencies isolated from your global Python installation:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks activation: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Running the test suite

```powershell
pytest
```

Runs the full test suite (transformers + generators) using isolated `tmp_path` fixtures — no real filesystem paths are touched.

---

## Information to have handy before running

For any migration you need:
- The **source project folder** path (containing the legacy `.java` files)

For **HANA Cloud (BTP CF)** mode you also need:

| What | Where to find it | Example |
|---|---|---|
| **CF API endpoint** | BTP Cockpit → Subaccount → Cloud Foundry → API Endpoint | `https://api.cf.us10.hana.ondemand.com` |
| **CF org and space names** | BTP Cockpit → Subaccount → Cloud Foundry | `my-org` / `dev` |
| **HANA Cloud service instance name** | `cf services` — the instance with plan `hdi-shared` | `my-app-hdi` |
| **Local dev HANA host** _(optional, for running locally)_ | BTP Cockpit → HANA Cloud → Open in HANA Database Explorer → connection info | `abc123.hana.ondemand.com` |
| **Local dev HDI schema + user** _(optional)_ | HANA Database Explorer → HDI container → bound user | `MY_SCHEMA` / `APP_USER` |
| **Path to `.dtdbtable` ZIP** _(optional)_ | Exported from SAP NWDS / provided by DBA | `C:\work\artifacts.zip` |

> **Tip:** Run `cf login` and `cf services` before starting the tool so you can copy-paste the service instance name exactly as it appears.

---

## Running the tool

### Interactive mode (recommended)

```powershell
python migrate.py "C:\path\to\legacy-java-project"
```

The tool scans the source, prints a summary, then asks you the questions below one by one.

### Non-interactive mode (CI / scripting)

```powershell
python migrate.py "C:\path\to\legacy-java-project" `
  --output "C:\path\to\output" `
  --group-id "com.example.myapp" `
  --artifact-id "my-app" `
  --persistence hana-cloud `
  --db-artifacts "C:\path\to\artifacts.zip" `
  --non-interactive
```

---

## CLI options

| Option | Short | Default | Description |
|---|---|---|---|
| `SOURCE_DIR` | — | required | Path to the legacy Java project root |
| `--output` | `-o` | `<parent>/<artifact-id>-springboot` | Output directory |
| `--base-package` | `-b` | auto-detected | Base Java package. Overrides auto-detection — **required** for `--non-interactive` if the source spans more than one top-level package (see [Q14](#q14-base-package-auto-detected-as-just-com)) |
| `--group-id` | `-g` | auto-detected | Maven group ID |
| `--artifact-id` | `-a` | source directory name | Maven artifact ID |
| `--persistence` | `-p` | `jpa` | `jpa`, `jdbc`, `sap`, or `hana-cloud` |
| `--spring-boot-version` | — | `3.2.5` | Spring Boot parent version |
| `--java-version` | — | `17` | Java compile target |
| `--db-artifacts` | `-d` | _(none)_ | Path to ZIP containing `.dtdbtable` files |
| `--unavailable-packages` | `-u` | _(none)_ | Comma-separated import prefixes to comment out with a TODO — for a codebase's own internal/proprietary packages the target environment doesn't have (see [Q15](#q15-my-codebase-has-its-own-internal-packages-that-dont-exist-in-the-target-environment)) |
| `--non-interactive` | — | `false` | Skip all prompts; use provided values |

---

## Prompts explained

### `[1/5]` Base package

```
  [1/5] Base package [com.example.myapp]:
```

The root Java package for the output project. The tool auto-detects it by scanning import statements; confirm or override. If the detection looks too deep (e.g., `com.example.myapp.controller`), shorten it to the correct root (e.g., `com.example.myapp`).

> In `--non-interactive` mode there's no prompt to catch a bad detection — if your source spans more than one top-level package (e.g. both `com.example.myapp.*` and `com.example.legacy.*`), pass `--base-package` explicitly. See [Q14](#q14-base-package-auto-detected-as-just-com).

---

### `[2/5]` Group ID

```
  [2/5] Group ID [com.example]:
```

Maven `<groupId>`. Typically the organisation/team prefix — everything up to the project name. Usually auto-derived from the base package.

---

### `[3/5]` Artifact ID

```
  [3/5] Artifact ID [my-app]:
```

Maven `<artifactId>` and also the CF application name. Defaults to the source folder name in kebab-case. This name appears verbatim in:
- `pom.xml` as `<artifactId>`
- `mta.yaml` as module and resource names (e.g., `my-app-app`, `my-app-db`, `my-app-hdi`)
- `application-cloud.properties` property key prefixes

---

### `[4/5]` Spring Boot version

```
  [4/5] Spring Boot version [3.2.5]:
```

Accept the default unless your BTP account has a specific runtime requirement. Spring Boot 3.x requires Java 17+ and uses Jakarta EE 9 packages (`jakarta.*` not `javax.*`).

---

### `[4b/5]` Java version

```
  [4b/5] Java version [17]:
```

Must align with what `sap_java_buildpack_jakarta` supports on your BTP subaccount. The default `17` is the LTS version supported by the Jakarta buildpack.

---

### `[5/5]` Persistence layer

```
  [5/5] Persistence layer:
         (1) Standard JPA   [DEFAULT]
         (2) JDBC
         (3) SAP-proprietary
         (4) HANA Cloud (BTP CF)
```

| Choice | Use when | What the tool generates |
|---|---|---|
| 1 — JPA | Migrating to any relational DB with `@Entity` annotations | `spring-boot-starter-data-jpa` + datasource placeholders in properties |
| 2 — JDBC | Using `JdbcTemplate` directly, no ORM | `spring-boot-starter-jdbc` |
| 3 — SAP | App uses custom SAP JDBC / EJB QL — flag for manual rewrite | Marks all DAO files with TODO comments |
| 4 — HANA Cloud | Deploying to BTP CF with SAP HANA Cloud | `ngdbc` driver, `application-cloud.properties`, `mta.yaml`, HDI artifacts |

---

### `[6/7]` BTP HDI service instance name _(hana-cloud only)_

```
  [6/7] BTP HDI service instance name [my-app-hdi]:
```

The name of the `hana / hdi-shared` service instance in your CF space. Run `cf services` before starting the tool and copy the name exactly — it appears verbatim in:

- `mta.yaml` → `resources.name`
- `application-cloud.properties` → `vcap.services.<name>.credentials.*`

> If the service doesn't exist yet: `cf create-service hana hdi-shared <name>`

---

### `[7/7]` DB artifacts ZIP _(hana-cloud only, optional)_

```
  [7/7] Do you have .dtdbtable files to convert to HANA HDI artifacts? [y/N]:
```

If you have SAP NWDS ABAP Dictionary table definitions exported as a ZIP:

- The ZIP may contain files at any depth; the tool finds all `*.dtdbtable` entries recursively
- `.xlf` companion files (translations) are ignored — descriptions come from the `.dtdbtable` files themselves
- Each table becomes a `db/src/<TABLE_NAME>.hdbtable` file
- Tables with no primary key defined in the source get one assigned heuristically and a `-- NOTE` comment — **review these before deploying to production**

---

## What the tool generates

```
<artifact-id>-springboot/
├── pom.xml                               Java 17, Spring Boot 3.x, ngdbc, Lombok, Actuator
├── package.json                          Root deploy script: mvn clean package → mbt build → cf deploy
├── manifest.yml                          Standalone CF push (single module)
├── mta.yaml                              MTA deploy (HDI deployer + Java app)
├── run-openrewrite.sh                    Optional further modernization — run later, in a connected environment
├── migration-report.md                   What was converted + every manual TODO item
├── db/                                   (hana-cloud only)
│   ├── src/
│   │   ├── .hdiconfig                    HDI plugin declarations — MUST be in src/
│   │   ├── .hdinamespace                 Empty namespace
│   │   └── *.hdbtable                    One file per table
│   └── package.json                      @sap/hdi-deploy entry point
└── src/
    ├── main/
    │   ├── java/<package>/
    │   │   ├── *Application.java         @SpringBootApplication main class
    │   │   ├── controller/               Transformed controllers
    │   │   ├── service/                  Transformed service interfaces + impls
    │   │   ├── dao/                      Transformed DAO interfaces + impls
    │   │   ├── model/                    Transformed entity/DTO classes
    │   │   ├── co/                       Enums — copied as-is
    │   │   └── utils/                    Utilities — copied with API-upgrade flags
    │   └── resources/
    │       ├── application.properties        Common settings + Actuator config
    │       ├── application-cloud.properties  BTP CF datasource (vcap.services.*)
    │       └── application-local.properties  Local dev datasource template
    └── test/
        └── java/<package>/               Test files routed here (if any detected)
```

> **Note:** Output file placement is driven by each file's own `package` declaration, not the source directory structure. Legacy projects stored in flat dot-named folders (`dao.impl/`, `service.impl/`, `dao.model.screen/`) are placed correctly without any pre-processing.

---

## Persistence modes

| Mode | What it does |
|---|---|
| `jpa` | Adds `spring-boot-starter-data-jpa`; javax→jakarta rewrites applied |
| `jdbc` | Adds `spring-boot-starter-jdbc`; javax→jakarta rewrites applied |
| `sap` | No JPA/JDBC dep added; every DAO/Repo file flagged with MANUAL TODO |
| `hana-cloud` | ngdbc driver, cloud properties, MTA yaml, HDI artifacts (if ZIP provided) |

---

## Automated modernization (OpenRewrite)

Every run also generates `run-openrewrite.sh` at the project root. It applies [OpenRewrite](https://docs.openrewrite.org/) recipes to the migrated code via Maven, going further than this tool's own regex-based transforms for generic (non-SAP) modernization.

**Why it's a separate script, not part of migration itself:** `migrate.py` is designed to run with zero network access (e.g. an air-gapped secure VDI). OpenRewrite's Maven plugin needs to download recipe artifacts from Maven Central, so it can't run at that point. Run the script later, from any environment with Maven repository access (e.g. a connected cloud IDE):

```bash
bash run-openrewrite.sh
```

No sign-up is required — it calls the open-source `rewrite-maven-plugin` directly against public Maven Central coordinates. (Moderne, the company behind OpenRewrite, sells a separate hosted platform for running recipes across many repositories at scale, but that's optional infrastructure, not a requirement for this script.)

**Recipes, in the order they run:**

| # | Recipe | Purpose |
|---|---|---|
| 1 | `UpgradeToJava25` | Bumps the language/compiler baseline first, so later recipes operate against the final target Java version |
| 2 | `JakartaEE11` | `javax.*` → `jakarta.*` namespace migration |
| 3 | `UpgradeSpringBoot_3_2` | Spring Boot framework + dependency version upgrade |
| 4 | `Log4jToSlf4j` | Apache Log4j API → SLF4J |
| 5 | `CommonStaticAnalysis` | Cleanup pass (unused imports, dead code) — must run last, since it cleans up debris left by the recipes above |

Order matters for two of these: `JakartaEE11` must run before `UpgradeSpringBoot_3_2` (which bundles its own partial Jakarta migration — running the fuller one first makes that step a no-op instead of redoing partial work), and `CommonStaticAnalysis` must always run last. The rest are independent of each other. Prerequisites: Maven and a JDK, plus Maven Central access from wherever you run it.

---

## Limitations

- **No semantic analysis.** Transformations are regex-based, not AST-based. Unusual formatting may not be detected, and — see the next point — the tool cannot safely rewrite a *usage* of a type, only the self-contained `import` line that brings it in.
- **Commenting an import doesn't fix usages elsewhere in the file.** This applies to every "comments out" category below (`com.sap.engine.*`, `com.sap.conn.jco.*`, `com.sap.bpm.*`, `com.sap.scheduler.*`, `javax.resource.cci.*`, `javax.ejb.*`/`javax.interceptor.*`/`org.springframework.ejb.*`, `javax.jws.*`, and anything passed via `--unavailable-packages`): if the type is also used as a field, a method parameter/return type, an annotation argument, or inside a method body, that usage still fails to compile as `cannot find symbol` — see [Q10](#q10-mvn-compile-still-fails-with-cannot-find-symbol-on-sapejbbpm-classes). Safely rewriting a usage (as opposed to a self-contained import line) needs real Java structural understanding — you can't blank out a method's return type without removing the whole method, and removing a method can break its callers elsewhere. That's out of scope for a regex-based tool.
- **SAP UME Security (`com.sap.security.*`) is the one exception** — imports stay live, and `StubGenerator` writes ten compilable stub classes/interfaces (`IUser`, `IPrincipal`, `IUserFactory`, `IRoleFactory`, `IGroup`, `IGroupFactory`, `IAuthenticator`, `UMException`, `UMFactory`, `ApplicationPropertiesChangeListener`) covering the most common `UMFactory.*` calls, throwing `UnsupportedOperationException` at runtime. This is best-effort, not exhaustive — an unusual UME class or `UMFactory` method not in that list will still fail as `cannot find symbol`.
- **SAP BPM (`com.sap.bpm.*`).** Being replaced by Build Process Automation (BPA) on BTP — there's no mechanical equivalent to migrate to yet. Imports are commented out; usages need a full rewrite once the BPA replacement is designed.
- **SAP Job Scheduler / MDB (`com.sap.scheduler.*`, `@MessageDriven`).** No Spring Boot equivalent — Spring Boot doesn't run inside an EJB container. Rewrite as a Spring `@Scheduled` task or `@JmsListener` depending on what triggered the original job.
- **JCA Connector Architecture (`javax.resource.cci.*`).** SAP RFC/BAPI-style resource adapter with no Spring Boot equivalent. Replace with the SAP JCo standalone jar (if licensed) or expose SAP via REST.
- **Missing third-party dependencies (e.g. Apache POI, `commonj.sdo`).** The tool only handles SAP-proprietary and removed-JDK packages — a genuinely missing but ordinary Maven dependency (like `org.apache.poi`) isn't auto-added, since guessing a version without knowing the project's constraints is riskier than just adding it yourself. `commonj.sdo` in particular is usually bundled with the app server/BPM runtime itself rather than a normal reusable artifact — that one likely needs rewriting away entirely, not a dependency add.
- **Internal/proprietary packages specific to one codebase** (a client's own utility packages, say) aren't hardcoded into the tool — pass them via `--unavailable-packages` per run instead. See [Q15](#q15-my-codebase-has-its-own-internal-packages-that-dont-exist-in-the-target-environment).
- **Java 9–17 deprecated APIs.** The tool _detects_ JAXB, `sun.*`, `SecurityManager`, boxed constructors, `finalize()`, and deprecated `Thread` methods, and records them in the migration report, but does **not** modify the source. Each item must be fixed manually.
- **No DB schema generation from Java.** Model/entity classes are transformed (javax→jakarta) but field definitions are not synthesised from source — you need the DB schema or `.dtdbtable` files.
- **JNDI DataSource.** `InitialContext` / `context.lookup` usages are flagged but not replaced. Wire Spring Boot datasource injection (`@Autowired DataSource`) manually.
- **No method-body rewriting.** Conditional logic, service calls, and DAO query strings are copied verbatim. Complex business logic will still compile, but runtime behaviour must be verified.

---

## Migration report

Every run produces `migration-report.md` in the output folder. It contains:

| Section | What it covers |
|---|---|
| **What was automatically converted** | Table of all automated transformations applied (logging, jakarta, EJB, enums, HDI, etc.) |
| **Manual action required** | One sub-heading per file, one bullet per `// TODO MANUAL` comment — paths are output-relative (e.g. `src\main\java\com\example\service\impl\FooServiceImpl.java`) |
| **Known patterns requiring follow-up** | Summary table per pattern family (SAP UME security, SAP platform API, JNDI, JCo) — shows every affected file for that family in one place |
| **Skipped files** | Files excluded because their package indicates a pre-existing Spring Boot scaffold, not legacy code |
| **Automated modernization (optional)** | Points to `run-openrewrite.sh` — see [Automated modernization (OpenRewrite)](#automated-modernization-openrewrite) |
| **Test files** | JUnit 4 → 5 checklist if any test files were detected |
| **Next steps** | Ordered checklist from `mvn compile` through to BTP CF deploy, including running `run-openrewrite.sh` |

The report has a **1:1 relationship** between `// TODO MANUAL` comments in source and bullet points in the "Manual action required" section. Every commented-out SAP import line produces its own bullet — not a single bullet per file.

---

## Troubleshooting FAQs

### Q1: Base package detected too deeply

**Symptom:** Tool suggests `com.example.myapp.controller` instead of `com.example.myapp`.

**Fix:** Override it at the `[1/5]` prompt by typing the correct root package. The scanner strips known leaf segments (`controller`, `service`, `model`, etc.) but may miss custom sub-packages.

---

### Q3: App crashes on BTP with "Failed to determine suitable jdbc url"

**Symptom:**
```
Failed to configure a DataSource: 'url' attribute is not specified and no embedded datasource could be configured.
```

**Cause:** The deprecated `java-cfenv-boot` 2.4.x library was designed for Spring Boot 2.x and silently fails to map `VCAP_SERVICES` on Spring Boot 3.x.

**Fix:** The tool no longer includes `java-cfenv-boot`. Instead, Spring Boot's built-in CF support maps `VCAP_SERVICES` to `vcap.services.*` properties automatically. The generated `application-cloud.properties` references them directly:
```properties
spring.datasource.url=jdbc:sap://${vcap.services.<service-name>.credentials.host}:...
```
If you see this error on an older generated project, remove `java-cfenv-boot` from `pom.xml` and add an `application-cloud.properties` file following the pattern above.

---

### Q4: `vcap.services.*` property cannot be resolved

**Symptom:**
```
Could not resolve placeholder 'vcap.services.my-app-hdi.credentials.host'
```

**Cause:** The service name in `application-cloud.properties` doesn't match the actual bound service instance name.

**Fix:**
```powershell
cf env <app-name>
```
Find the `VCAP_SERVICES` block and check the `"name"` field of the bound service. Update the property key in `application-cloud.properties` to match exactly (it is case-sensitive).

---

### Q5: Wrong buildpack — `sap_java_buildpack` vs `sap_java_buildpack_jakarta`

**Symptom:** App starts but fails with `ClassNotFoundException` for `jakarta.*` classes, or `javax.*` classes are not found.

**Cause:** Spring Boot 3.x uses Jakarta EE 9 (`jakarta.*` namespace). The older `sap_java_buildpack` targets Java EE 8 (`javax.*`). Using it with Spring Boot 3.x causes class loading failures at runtime.

**Fix:** Use `sap_java_buildpack_jakarta` in both `manifest.yml` and `mta.yaml`:
```yaml
# manifest.yml
buildpacks:
  - sap_java_buildpack_jakarta

# mta.yaml
parameters:
  buildpack: sap_java_buildpack_jakarta
```
The tool generates the correct buildpack name by default.

---

### Q6: HDI make failed — "N files to deploy, 0 to undeploy... failed"

**Cause 1 — `.hdiconfig` in wrong location:**
`.hdiconfig` is in `db/` instead of `db/src/`. The HDI deployer only uploads the contents of `src/` to the HDI container — config files outside `src/` are never seen by HANA.

**Fix:** Ensure `.hdiconfig` and `.hdinamespace` are inside `db/src/`, not in `db/`.

**Cause 2 — Table without PRIMARY KEY:**
HANA Cloud enforces that all column store tables must have a primary key.

**Fix:** Add `PRIMARY KEY (...)` to every `.hdbtable` file. The tool handles this automatically using a heuristic; look for `-- NOTE:` comments in generated files where manual review is needed.

---

### Q7: `hana` service plan — `schema` vs `hdi-shared`

**Symptom:** HDI artifacts cannot be deployed; or the MTA resource type doesn't match.

**Cause:** The `schema` plan creates a plain database schema without an HDI container. HDI artifacts (`.hdbtable` etc.) require an HDI container, which is provided by the `hdi-shared` plan.

**Fix:**
```powershell
# Create the correct service
cf create-service hana hdi-shared my-app-hdi

# Verify
cf services
```
Update `mta.yaml` → `resources.name` and `application-cloud.properties` with the new instance name.

---

### Q8: `cf deploy` returns "command not found"

**Symptom:** `cf: 'deploy' is not a registered command`

**Fix:** Install the CF multiapps plugin:
```powershell
cf install-plugin multiapps
```

---

### Q9: HDI deployer succeeds but Java app fails (or vice versa)

The two MTA modules are independent. A failure in one does not roll back the other.

- Check the Java app log: `cf logs <artifact-id>-app --recent`
- Check the HDI deployer log: `cf logs <artifact-id>-db --recent`

After fixing the failing module, retry without re-running the succeeding one:
```powershell
cf deploy -i <deployment-id> -a retry
```

Get the deployment ID from the `cf deploy` output, or run `cf mta-ops`.

---

### Q10: `mvn compile` still fails with `cannot find symbol` on SAP/EJB/BPM classes

**Symptom:** Even after migration, `mvn compile` reports errors like:
```
error: cannot find symbol
  symbol:   class IUser
  location: class ...ServiceImpl
```
or the same shape for BPM (`TaskDetail`, `Status`), scheduler/MDB (`MDBJobImplementation`, `JobContext`), EJB-container (`Local`, `TransactionManagementType`), or JAX-WS (`WebMethod`, `WebParam`) types.

**Cause:** The type is referenced in method signatures, field declarations, annotation arguments, or method bodies — not just in the `import` statement. The tool only comments out `import` lines (or, for `com.sap.security.api.*`, generates a stub); usages in code remain untouched either way. See [Limitations](#limitations) for why this can't be done safely by a regex-based tool.

**Fix:** Search for all uses of the missing type name in the file and either remove them or replace them with the Spring equivalent:
- `com.sap.security.api.IUser` → inject `java.security.Principal` via a method parameter annotated with `@AuthenticationPrincipal`, or extend the stub set in `stub_generator.py` if the call is to a `UMFactory` method not yet stubbed.
- `com.sap.bpm.*` types → no mechanical equivalent yet; rewrite against BTP Build Process Automation once that's designed.
- MDB/scheduler types (`MDBJobImplementation`, `JobContext`, `@MessageDriven`) → rewrite the class as a Spring `@Scheduled` task or `@JmsListener`.
- JCA types (`javax.resource.cci.*`) → rewrite using the SAP JCo standalone jar or a REST call to SAP.

---

### Q11: What do `// TODO MANUAL` comments mean?

Every line the tool comments out — because it references a SAP or otherwise unavailable library — is prefixed with:

```java
// TODO MANUAL — <reason>
// import com.sap.security.api.IUser;
```

Each such line also has a corresponding bullet in `migration-report.md` under that file's heading. The goal is a 1:1 relationship: every commented-out import in source has exactly one entry in the report, so the report is a complete work list.

Search for `TODO MANUAL` in the generated project to find all items at once:
```powershell
# PowerShell
Get-ChildItem -Recurse -Filter *.java | Select-String "TODO MANUAL"
```

---

### Q12: Some files from the source were not included in the output

**Symptom:** A few `.java` files from the legacy source are missing from the output.

**Cause:** The tool skips files whose `package` declaration does not belong to the legacy codebase — typically files that were already part of a nascent Spring Boot scaffold committed alongside the legacy source. These are listed in the "Skipped files" section of `migration-report.md`.

**What to do:** Review the skipped list. If a file was incorrectly identified as scaffold (e.g., a utility class whose package happens to contain a scaffold-like fragment), copy it manually from the source and adjust its package declaration.

---

### Q13: Migration report shows Java 9–17 deprecation warnings

**Symptom:** `migration-report.md` contains items like:

```
MANUAL — Java version upgrade: Boxed-type constructors (new Integer(), ...) are deprecated for removal since Java 9.
```

**Cause:** The source uses APIs that were deprecated or removed between Java 8 and Java 17. The tool detects these patterns but does not rewrite them.

**Common fixes:**

| Deprecated pattern | Replacement |
|---|---|
| `new Integer(x)` | `Integer.valueOf(x)` |
| `new Long(x)` | `Long.valueOf(x)` |
| `import javax.xml.bind.*` | Add `jakarta.xml.bind:jakarta.xml.bind-api:4.0.0` to `pom.xml` |
| `import sun.misc.*` | Use `java.util.Base64` etc. (standard replacements) |
| `Thread.stop()` | `Thread.interrupt()` + check `isInterrupted()` |
| `System.setSecurityManager(...)` | Remove — handled by Spring Security |
| `protected void finalize()` | `AutoCloseable` + try-with-resources |

These are compile warnings in Java 17 and compile errors in Java 21+. Fix them before upgrading the Java version target in `pom.xml`.

---

### Q14: Base package auto-detected as just `com`

**Symptom:** In `--non-interactive` mode, the generated `Application.java` ends up at `src/main/java/com/FooApplication.java` with `package com;` — and possibly a *second*, stray `@SpringBootApplication` class if you'd already generated once before without noticing.

**Cause:** Base package auto-detection works by taking the longest common package-segment prefix across every scanned file. If the source spans more than one top-level package (e.g. it mixes `com.example.myapp.*` and `com.example.legacy.*`), the common prefix collapses to just `com`, since the two diverge immediately after that. Interactive mode catches this at the `[1/5]` prompt (you'd notice and correct a `com` default); non-interactive mode has no such checkpoint.

**Fix:** Pass `--base-package` explicitly:
```powershell
python migrate.py "C:\path\to\legacy-java-project" --base-package "com.example.myapp" --non-interactive ...
```
If a stray `com/FooApplication.java` was already generated by a previous run, delete it manually — the tool doesn't clean up files from prior runs, it only (re)writes what the current run produces.

---

### Q15: My codebase has its own internal packages that don't exist in the target environment

**Symptom:** `mvn compile` fails with `package does not exist` for packages that aren't SAP's own (e.g. an internal shared-utilities package specific to your organization), and the tool doesn't flag them by default.

**Cause:** This tool stays generic on purpose — it never hardcodes any specific organization's or project's package names (see [CLAUDE.md](CLAUDE.md)'s "No client-specific strings" rule). Only genuinely SAP-proprietary and removed-JDK packages are recognized automatically.

**Fix:** Pass `--unavailable-packages` with a comma-separated list of prefixes:
```powershell
python migrate.py "C:\path\to\legacy-java-project" --unavailable-packages "com.example.myapp.internal,com.example.sharedutils" --non-interactive ...
```
Each matching import gets commented out with a `// TODO MANUAL` marker, same as the built-in SAP categories. As always, this only fixes the import line — usages elsewhere in the file still need manual attention (see [Q10](#q10-mvn-compile-still-fails-with-cannot-find-symbol-on-sapejbbpm-classes)).
