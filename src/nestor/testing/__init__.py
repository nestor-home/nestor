"""Test kit for Nestor and its adapters: doubles and contract suites, one module per domain module.

An adapter proves it honours a port by running the matching suite:

    class TestHermesExecutor(ExecutorContract):
        def executor(self) -> Executor: ...

The suites import nothing outside the standard library, so the kit ships with the package.
"""
