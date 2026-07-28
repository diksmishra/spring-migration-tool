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

1. **Scans** your legacy project and classifies all Java files (controllers, services, DAOs, models).
2. **Detects** SAP-specific patterns: `com.sap.tc.logging`, `javax.persistence`, JNDI lookups, SAP JCo, SAP UME Security.
3. **Transforms** every `.java` file:
   - Replaces `SimpleLogger` / `Location` with SLF4J (`Logger` / `LoggerFactory`)
   - Rewrites `javax.*` → `jakarta.*` (required for Spring Boot 3.x / Jakarta EE 9+)
   - Converts EJB annotations: `@Stateless` / `@Stateful` → `@Service`, `@EJB` → `@Autowired`
   - Removes OpenJPA-specific imports
4. **Generates** Spring Boot scaffold files (`pom.xml`, main class, properties, `manifest.yml`, `mta.yaml`).
5. **Generates** HANA Cloud HDI artifacts (`*.hdbtable`, `.hdiconfig`, `.hdinamespace`) from `.dtdbtable` ZIP exports.
6. **Copies** non-Java resources (XML, properties, YAML, JSON) into the output tree.
7. **Writes** `migration-report.md` listing every manual-action item.

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
| `--group-id` | `-g` | auto-detected | Maven group ID |
| `--artifact-id` | `-a` | source directory name | Maven artifact ID |
| `--persistence` | `-p` | `jpa` | `jpa`, `jdbc`, `sap`, or `hana-cloud` |
| `--spring-boot-version` | — | `3.2.5` | Spring Boot parent version |
| `--java-version` | — | `17` | Java compile target |
| `--db-artifacts` | `-d` | _(none)_ | Path to ZIP containing `.dtdbtable` files |
| `--non-interactive` | — | `false` | Skip all prompts; use provided values |

---

## Prompts explained

### `[1/5]` Base package

```
  [1/5] Base package [com.example.myapp]:
```

The root Java package for the output project. The tool auto-detects it by scanning import statements; confirm or override. If the detection looks too deep (e.g., `com.example.myapp.controller`), shorten it to the correct root (e.g., `com.example.myapp`).

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
├── pom.xml                               Java 17, Spring Boot 3.x, ngdbc, Actuator
├── manifest.yml                          Standalone CF push (single module)
├── mta.yaml                              MTA deploy (HDI deployer + Java app)
├── migration-report.md                   What was converted + manual TODOs
├── db/                                   (hana-cloud only)
│   ├── src/
│   │   ├── .hdiconfig                    HDI plugin declarations — MUST be in src/
│   │   ├── .hdinamespace                 Empty namespace
│   │   └── *.hdbtable                    One file per table
│   └── package.json                      @sap/hdi-deploy entry point
└── src/main/
    ├── java/…/
    │   ├── *Application.java             @SpringBootApplication main class
    │   └── (transformed source files)
    └── resources/
        ├── application.properties        Common settings + Actuator config
        ├── application-cloud.properties  BTP CF datasource (vcap.services.*)
        └── application-local.properties  Local dev datasource template
```

---

## Persistence modes

| Mode | What it does |
|---|---|
| `jpa` | Adds `spring-boot-starter-data-jpa`; javax→jakarta rewrites applied |
| `jdbc` | Adds `spring-boot-starter-jdbc`; javax→jakarta rewrites applied |
| `sap` | No JPA/JDBC dep added; every DAO/Repo file flagged with MANUAL TODO |
| `hana-cloud` | ngdbc driver, cloud properties, MTA yaml, HDI artifacts (if ZIP provided) |

---

## Limitations

- **No semantic analysis.** Transformations are regex-based. Unusual formatting of SAP logging calls may not be detected.
- **No SAP JCo replacement.** Files using `com.sap.conn.jco` are flagged but not transformed. RFC/BAPI calls require manual rewriting.
- **No SAP UME Security replacement.** Files using `com.sap.security.*` are flagged; Spring Security setup is manual.
- **No DB schema.** Model/entity classes are transformed (javax→jakarta) but field definitions are not generated — you need the DB schema or `.dtdbtable` files.
- **JNDI DataSource.** The tool flags `InitialContext` / `context.lookup` usages but does not replace them — Spring Boot datasource injection must be wired manually.
- **javalang parse errors.** The tool falls back to regex if javalang cannot parse a file. Structural analysis may be less accurate for complex files.

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
