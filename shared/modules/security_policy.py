"""
Security policy definitions for NEXUS module system.

Single source of truth for import restrictions and security policies.

Policy violations are terminal failures — no retry (EDMO doc T2 compensation scope).
"""
from typing import Set

# Forbidden imports (security baseline)
# These imports are always forbidden in generated adapter code
FORBIDDEN_IMPORTS: Set[str] = {
    "os.system",
    "subprocess",
    "eval",
    "exec",
    "__import__",
    "compile",
    "importlib.import_module",
}

# Safe built-in functions allowed in sandbox execution
# These are permitted for basic adapter operations
SAFE_BUILTINS: Set[str] = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "classmethod", "complex", "delattr", "dict", "dir",
    "divmod", "enumerate", "filter", "float", "format", "frozenset",
    "getattr", "hasattr", "hash", "hex", "id", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next",
    "object", "oct", "ord", "pow", "print", "property", "range", "repr",
    "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
    "str", "sum", "super", "tuple", "type", "vars", "zip",
}
