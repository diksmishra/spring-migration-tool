"""
Generates compilable stub classes for SAP APIs that have no Spring Boot
equivalent. Stubs live in the original packages so existing imports compile
without modification; they throw UnsupportedOperationException at runtime,
making it obvious which call paths still need replacement.

Also generates dynamic stubs for --unavailable-packages types, synthesized
from this run's usage_harvester findings (self.config.scan_result
['unavailable_pkg_usages']). These are single-run, single-app only — nothing
here persists between runs, developers, or VDIs. See CLAUDE.md.
"""
from pathlib import Path
from typing import Dict, Tuple
from migration_tool.config import MigrationConfig

# JDK collection names safe to trust in a harvested return-type guess — each
# needs a java.util import added.
_SAFE_JDK_COLLECTION_NAMES = ('List', 'Set', 'Map', 'Collection', 'Optional')
# java.lang types need no import at all — always safe to trust verbatim.
_SAFE_JAVA_LANG_NAMES = (
    'String', 'Object', 'Integer', 'Long', 'Double', 'Float', 'Boolean',
    'Short', 'Byte', 'Character', 'Number', 'Void',
)
# Primitives, likewise always safe verbatim (including void for a call used as
# a bare statement whose declared "return type" doesn't apply, though harvest()
# never actually infers void — kept here for completeness).
_SAFE_PRIMITIVES = ('int', 'long', 'double', 'float', 'boolean', 'byte', 'short', 'char', 'void')
# Anything else (a custom, non-JDK type name) falls back to Object — we can't
# be sure it's importable/resolvable in the generated project.


def _resolve_return_type(raw, imports: set) -> Tuple[str, bool]:
    """Returns (type_string, was_guessed)."""
    if not raw:
        return 'Object', True
    head = raw.split('<', 1)[0].strip().rstrip('[]')
    if head in _SAFE_JDK_COLLECTION_NAMES:
        imports.add(f'java.util.{head}')
        return raw, False
    if head in _SAFE_JAVA_LANG_NAMES or head in _SAFE_PRIMITIVES:
        return raw, False
    return 'Object', True


def _synthesize_stub(full_dotted_name: str, shape: dict) -> Tuple[str, str]:
    """Build a compilable interface from a usage_harvester shape dict.

    Always an interface, never a class: Java interfaces can carry both
    abstract instance methods and `static` methods with bodies (Java 8+),
    which avoids needing to guess class-vs-interface at all.
    """
    package, _, simple_name = full_dotted_name.rpartition('.')
    imports: set = set()
    method_blocks = []

    for key in sorted(shape.get('methods', {})):
        method = shape['methods'][key]
        method_name, _, arg_count_str = key.rpartition('#')
        arg_count = int(arg_count_str) if arg_count_str else 0
        params = ', '.join(f'Object arg{i}' for i in range(arg_count))
        return_type, guessed = _resolve_return_type(method.get('return_type'), imports)
        comment = ''
        if method.get('from_cache'):
            comment += (
                '    // inherited from a previous migration on this machine — this app\'s\n'
                '    // own code never called it; confirm the signature before relying on it\n'
            )
        if guessed:
            comment += '    // return type guessed as Object — verify\n'

        if method.get('static'):
            method_blocks.append(
                f'{comment}    static {return_type} {method_name}({params}) {{\n'
                f'        throw new UnsupportedOperationException(\n'
                f'            "Auto-generated stub — replace with the real implementation");\n'
                f'    }}\n'
            )
        else:
            method_blocks.append(f'{comment}    {return_type} {method_name}({params});\n')

    import_block = ''.join(f'import {imp};\n' for imp in sorted(imports))
    if import_block:
        import_block += '\n'
    package_line = f'package {package};\n\n' if package else ''

    source = (
        f'{package_line}'
        f'{import_block}'
        '/**\n'
        ' * Auto-generated stub — discovered from how this codebase actually uses\n'
        ' * this type, not a real API definition. Replace with the real\n'
        ' * implementation, or remove once the calling code is rewritten.\n'
        ' */\n'
        f'public interface {simple_name} {{\n'
        + '\n'.join(method_blocks) +
        '}\n'
    )
    rel_path = full_dotted_name.replace('.', '/') + '.java'
    return rel_path, source

# Each entry: (relative_path_under_src_main_java, java_source)
_STUBS = [
    (
        'com/sap/security/api/IUser.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security principal access. */
public interface IUser {
    String getUniqueName();
    String getLogonName();
    String getFirstName();
    String getLastName();
    String getEmail();
    String getAttribute(String namespace, String name);
    String[] getAttributeList(String namespace, String name);
}
'''
    ),
    (
        'com/sap/security/api/IPrincipal.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security principal/authority access. */
public interface IPrincipal {
    String getUniqueName();
    String getDisplayName();
    String getDescription();
}
'''
    ),
    (
        'com/sap/security/api/IUserFactory.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security UserDetailsService. */
public interface IUserFactory {
    IUser getUser(String uniqueName) throws UMException;
    IUser getUserByLogonID(String logonId) throws UMException;
}
'''
    ),
    (
        'com/sap/security/api/IRoleFactory.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security GrantedAuthority / role checks. */
public interface IRoleFactory {
    boolean isUserInRole(String uniqueName, String roleName) throws UMException;
}
'''
    ),
    (
        'com/sap/security/api/IGroup.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security GrantedAuthority / group membership checks. */
public interface IGroup {
    String getUniqueName();
    String getDisplayName();
}
'''
    ),
    (
        'com/sap/security/api/IGroupFactory.java',
        '''\
package com.sap.security.api;

/** Stub — replace with Spring Security GrantedAuthority / group lookups. */
public interface IGroupFactory {
    IGroup getGroupByUniqueName(String uniqueName) throws UMException;
}
'''
    ),
    (
        'com/sap/security/api/IAuthenticator.java',
        '''\
package com.sap.security.api;

/** Stub — replace with SecurityContextHolder.getContext().getAuthentication(). */
public interface IAuthenticator {
    IUser getLoggedInUser();
}
'''
    ),
    (
        'com/sap/security/api/UMException.java',
        '''\
package com.sap.security.api;

/** Stub exception used by IUserFactory / IRoleFactory stubs. */
public class UMException extends Exception {
    public UMException(String message) { super(message); }
    public UMException(String message, Throwable cause) { super(message, cause); }
}
'''
    ),
    (
        'com/sap/security/api/UMFactory.java',
        '''\
package com.sap.security.api;

/**
 * Stub — all methods throw UnsupportedOperationException.
 * Replace with Spring Security SecurityContextHolder / UserDetailsService.
 */
public class UMFactory {
    private UMFactory() {}

    public static UMFactory getUMFactory() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — replace with Spring Security");
    }

    public static IUser getAuthenticatedUser() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — use SecurityContextHolder.getContext().getAuthentication()");
    }

    public static IUserFactory getUserFactory() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — replace with UserDetailsService");
    }

    public static IRoleFactory getRoleFactory() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — replace with Spring Security role checks");
    }

    public static IGroupFactory getGroupFactory() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — replace with Spring Security group/authority checks");
    }

    public static IAuthenticator getAuthenticator() {
        throw new UnsupportedOperationException(
            "SAP UMFactory stub — use SecurityContextHolder.getContext().getAuthentication()");
    }
}
'''
    ),
    (
        'com/sap/engine/services/configuration/appconfiguration/ApplicationPropertiesChangeListener.java',
        '''\
package com.sap.engine.services.configuration.appconfiguration;

/**
 * Stub interface — the class that implements this must have it removed from
 * its implements clause (utils_transformer handles this automatically).
 * Replace with @RefreshScope (Spring Cloud Config) or @ConfigurationProperties.
 */
public interface ApplicationPropertiesChangeListener {
    void propertiesChanged();
}
'''
    ),
]


class StubGenerator:
    def __init__(self, config: MigrationConfig):
        self.config = config

    def generate(self) -> None:
        """Write all stub source files into the output project's src/main/java tree."""
        src_root = Path(self.config.output_dir) / 'src' / 'main' / 'java'
        for rel_path, java_source in _STUBS:
            dest = src_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(java_source, encoding='utf-8')

        harvested = self.config.scan_result.get('unavailable_pkg_usages', {})
        for full_dotted_name, shape in harvested.items():
            rel_path, java_source = _synthesize_stub(full_dotted_name, shape)
            dest = src_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(java_source, encoding='utf-8')
