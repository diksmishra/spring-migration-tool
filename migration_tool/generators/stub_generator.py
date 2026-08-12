"""
Generates compilable stub classes for SAP APIs that have no Spring Boot
equivalent. Stubs live in the original packages so existing imports compile
without modification; they throw UnsupportedOperationException at runtime,
making it obvious which call paths still need replacement.
"""
from pathlib import Path
from migration_tool.config import MigrationConfig

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
