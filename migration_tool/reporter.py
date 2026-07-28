from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from migration_tool.config import MigrationConfig


class Reporter:
    def __init__(self, config: MigrationConfig):
        self.config = config
        self._files: List[Dict[str, Any]] = []

    def record_file(self, src_path: Path, rel_path: Path, todos: List[str]):
        self._files.append({'path': str(rel_path), 'todos': todos})

    def get_summary(self) -> Dict[str, int]:
        total_todos = sum(len(f['todos']) for f in self._files)
        return {'transformed': len(self._files), 'todo_count': total_todos}

    def write(self, report_path: Path):
        now  = datetime.now().strftime('%Y-%m-%d %H:%M')
        has_hdi = bool(self.config.db_artifacts_zip)

        lines = [
            '# Migration Report',
            f'\nGenerated: {now}',
            f'\nSource: `{self.config.source_dir}`',
            f'Output: `{self.config.output_dir}`',
            f'Persistence mode: **{self.config.persistence_mode}**',
            '\n---\n',
            '## What was automatically converted\n',
            '| # | Transformation | Details |',
            '|---|---|---|',
            '| 1 | SAP logging → SLF4J | All `com.sap.tc.logging.*` replaced in every file |',
            '| 2 | javax.* → jakarta.* | persistence, transaction, validation, servlet packages |',
            '| 3 | EJB annotations | `@Stateless`→`@Service`, `@EJB`→`@Autowired` where present |',
            '| 4 | OpenJPA imports | Removed `org.apache.openjpa.*` (standard JPA equivalents work) |',
            '| 5 | pom.xml | Generated with Spring Boot parent, persistence deps, and Actuator |',
            '| 6 | Application main class | `@SpringBootApplication` entry point created |',
            '| 7 | application.properties | Common settings + Actuator config generated |',
        ]

        if self.config.persistence_mode == 'hana-cloud':
            lines.append('| 8 | application-cloud.properties | BTP CF datasource via `vcap.services.*` |')
            if has_hdi:
                lines.append('| 9 | HDI artifacts | `.hdbtable` files + `.hdiconfig` + `mta.yaml` generated in `db/` |')

        lines += ['\n---\n', '## Manual action required\n']

        files_with_todos = [(f['path'], f['todos']) for f in self._files if f['todos']]
        if not files_with_todos:
            lines.append('_No manual items identified. Review the output carefully before deploying._\n')
        else:
            for file_path, todos in files_with_todos:
                lines.append(f'### `{file_path}`\n')
                for todo in todos:
                    lines.append(f'- {todo}')
                lines.append('')

        # Known patterns
        scan       = self.config.scan_result
        todo_global = scan.get('todo_patterns', {})

        lines += ['\n---\n', '## Known patterns requiring follow-up\n']

        if todo_global.get('jndi'):
            lines.append('### JNDI DataSource Lookups\n')
            lines.append('Replace `new InitialContext()` / `context.lookup(...)` with Spring Boot DataSource injection:\n')
            lines.append('```properties')
            lines.append('spring.datasource.url=jdbc:db2://HOST:PORT/DB')
            lines.append('spring.datasource.username=user')
            lines.append('spring.datasource.password=pass')
            lines.append('```')
            lines.append('\nAffected files:')
            for f in todo_global['jndi']:
                lines.append(f'- `{f}`')
            lines.append('')

        if todo_global.get('sap_security'):
            lines.append('### SAP UME Security\n')
            lines.append('`com.sap.security.api.*` must be replaced with Spring Security.\n')
            lines.append('Recommended: configure `spring-boot-starter-security` + implement `UserDetailsService`.\n')
            lines.append('Affected files:')
            for f in todo_global['sap_security']:
                lines.append(f'- `{f}`')
            lines.append('')

        if todo_global.get('sap_jco'):
            lines.append('### SAP JCo (Java Connector)\n')
            lines.append("SAP JCo is SAP's proprietary RFC/BAPI connector — no direct Spring Boot equivalent.\n")
            lines.append('Options: (a) use SAP JCo standalone if the license allows, (b) expose SAP via REST.\n')
            lines.append('Affected files:')
            for f in todo_global['sap_jco']:
                lines.append(f'- `{f}`')
            lines.append('')

        # Next steps
        lines += ['\n---\n', '## Next steps (in order)\n']

        if self.config.persistence_mode == 'hana-cloud':
            svc = self.config.hdi_service_name or 'YOUR_HDI_SERVICE_INSTANCE'
            lines += [
                '1. Run `mvn compile` — fix any remaining compilation errors.',
                '2. Fill in `src/main/resources/application-local.properties` with your personal HANA Cloud dev credentials.',
                '3. Test locally: `mvn spring-boot:run -Dspring-boot.run.profiles=local`',
                '4. Add real field definitions to model/DTO classes (requires the HDI container schema).',
                '5. Implement service layer business logic.',
                '6. Implement DAO/repository layer (Spring Data JPA repositories or JdbcTemplate).',
                '7. Configure Spring Security if the app requires authentication.',
                '8. Write unit and integration tests.',
            ]
            if has_hdi:
                lines += [
                    f'9. Run `npm install` inside `db/` to install `@sap/hdi-deploy`.',
                    f'10. Verify the HDI service instance name in `mta.yaml` matches `cf services` output.',
                    '11. Build: `npm run deploy` (from project root — runs mvn + mbt build + cf deploy)',
                    '12. Check: `cf logs <app>-app --recent` and `cf logs <app>-db --recent`',
                ]
            else:
                lines += [
                    f'9. Update `mta.yaml` — set the HDI service instance name (`{svc}`) to match `cf services`.',
                    '10. Build the JAR: `mvn package -DskipTests`',
                    '11. Deploy to BTP CF: `cf push` (standalone) or `mbt build && cf deploy mta_archives/*.mtar` (MTA)',
                    '12. Verify endpoints: `cf logs <app-name>-app --recent`',
                ]
        else:
            lines += [
                '1. Run `mvn compile` from the output directory — fix any remaining compilation errors.',
                '2. Fill in `application.properties` with real datasource credentials.',
                '3. Add real field definitions to model/DTO classes (requires DB schema).',
                '4. Implement service layer business logic.',
                '5. Implement DAO/repository layer (use Spring Data JPA or JdbcTemplate).',
                '6. Configure Spring Security if the app requires authentication.',
                '7. Write unit and integration tests.',
                '8. Run `mvn spring-boot:run` and validate endpoints.',
            ]

        report_path.write_text('\n'.join(lines), encoding='utf-8')
