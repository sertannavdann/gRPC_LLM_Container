# Deferred Items

Out-of-scope discoveries logged during plan execution (not fixed — pre-existing,
unrelated to the current task's changes).

## 08-02 Task 2

- **`tests/unit/test_module_tools.py` fails at collection when run standalone**
  (`AttributeError: module 'tools.builtin' has no attribute 'module_builder'`).
  Root cause: `tools.builtin.module_builder` imports generated gRPC proto
  modules (`llm_service.llm_pb2`, `llm_service.llm_pb2_grpc`) that aren't
  present in this environment; other suites (e.g.
  `tests/integration/cross_feature/conftest.py`'s `setup_builder` fixture)
  work around this by mocking `sys.modules` before import, but
  `tests/unit/test_module_tools.py` does not do this itself. Confirmed
  pre-existing: byte-identical to the file at commit
  `956ab7c0134897a4a242ccef64ab0e728a40b52d` (base of this plan), and the
  same collection error reproduces with the ORIGINAL (pre-08-02)
  `module_installer.py` when run standalone without manual proto mocking.
  When manually mocked (`sys.modules['llm_service'] = MagicMock()` etc.
  before import), all 26 tests in the file pass, confirming the actual
  test logic is sound and unaffected by 08-02's changes.
  Out of scope for 08-02 — not touched.
