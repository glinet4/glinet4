# Minimal stub for the three crypt handlers glinet4._transport imports.
# passlib.hash replaces itself at runtime with a lazy-loading proxy object
# (passlib/registry.py's _PasslibRegistryProxy), so mypy cannot infer real
# attribute types from source; this covers only what this package touches.

class _CryptHandler:
    def using(self, *, salt: str = ..., rounds: int = ...) -> _CryptHandler: ...
    def hash(self, secret: str) -> str: ...

md5_crypt: _CryptHandler
sha256_crypt: _CryptHandler
sha512_crypt: _CryptHandler
