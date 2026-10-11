# Contributing to BengkelStack

Thank you for your interest in contributing to **BengkelStack: The Edge-First Workshop Operating System**!

We adhere to rigorous software engineering disciplines, including **5-Gate Enterprise SDLC**, **Test-Driven Development (TDD)**, and a **Zero-Dependency Core Philosophy**.

---

## 1. Core Engineering Principles (The Ponytail Ladder)

Before writing any code or proposing abstractions:
1. **YAGNI (You Aren't Gonna Need It):** Question whether speculative features need to exist at all.
2. **Python Standard Library First:** The core runtime server and database persistence layer must remain zero-dependency (`http.server`, `sqlite3`, `urllib.parse`, `json`, `difflib`, `re`, `secrets`). Do not add external `pip` dependencies to the core runtime unless approved in an ADR.
3. **Shortest Working Diff:** Deletion over addition. Clean, minimal, readable code wins over clever meta-programming.
4. **Deterministic Invariants:** Every transaction modifying inventory or billing must maintain 100% mathematical integrity.

---

## 2. Test-Driven Development (TDD) Rule

We enforce the **Iron Law of TDD**:
```text
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST (RED -> GREEN -> REFACTOR)
```

1. **RED:** Write a minimal failing test in `tests/test_<feature>.py`. Run it and confirm expected failure.
2. **GREEN:** Write the minimal implementation code to pass the test.
3. **REFACTOR:** Clean up code, remove duplication, and ensure all tests remain green.

Run all tests before submitting any PR:
```bash
python -m unittest discover -s tests
```
All **74+ test cases** must pass with **0 failures and 0 warnings**.

---

## 3. Pull Request Guidelines

1. **Branch Naming:** Use descriptive branch names:
   - `feat/invoice-scanner`
   - `fix/tax-rounding-bug`
   - `docs/architecture-update`
2. **Commit Messages:** Follow Conventional Commits format:
   - `feat(pricing): add custom model installation fee override`
   - `fix(security): sanitize customer input string against XSS`
   - `test(matcher): add fuzzy sequence matcher test cases`
3. **PR Description:** Include:
   - What problem does this PR solve?
   - Which tests were added or executed?
   - Relevant issue or ADR references.
