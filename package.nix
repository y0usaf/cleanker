{pkgs}:
pkgs.stdenv.mkDerivation {
  pname = "cleanker";
  version = "1";
  src = ./.;
  nativeBuildInputs = [pkgs.makeWrapper];
  nativeCheckInputs = [pkgs.git pkgs.ast-grep pkgs.nodejs];
  doCheck = true;
  checkPhase = ''
            ${pkgs.python3}/bin/python3 -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' $src/cleanker.py
            cleanker() { (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py "$@"); }
            tmp=$(mktemp -d)
            export HOME=$tmp
            git -C "$tmp" init -q
            git -C "$tmp" config user.email test@example.com
            git -C "$tmp" config user.name test
            git -C "$tmp" config --local cleanker.policy true
            printf 'hi\n' > "$tmp/README.md"
            git -C "$tmp" add -A
            git -C "$tmp" -c core.hooksPath=/dev/null commit -qm init
            printf '# bad\nx = 1\n' > "$tmp/a.py"
            git -C "$tmp" add a.py
            if cleanker hook; then
              echo "cleanker check: gate did not block a staged python comment" >&2
              exit 1
            fi
            cleanker clean > /dev/null
            git -C "$tmp" add -A
            grep -qx 'x = 1' "$tmp/a.py"
            cleanker hook
            printf '// bad\nfn main() {}\n' > "$tmp/a.rs"
            git -C "$tmp" add a.rs
            if cleanker hook; then
              echo "cleanker check: gate did not block a staged rust comment" >&2
              exit 1
            fi
            printf '// SPDX-License-Identifier: MIT\n/// Prose doc comment.\nfn main() {\n    // plain comment\n}\n' > "$tmp/b.rs"
            git -C "$tmp" add b.rs
            if cleanker hook; then
              echo "cleanker check: gate did not block a staged rust doc comment" >&2
              exit 1
            fi
            cleanker clean > /dev/null
            git -C "$tmp" add -A
            grep -qx '// SPDX-License-Identifier: MIT' "$tmp/b.rs"
            if grep -q 'Prose doc comment' "$tmp/b.rs"; then
              echo "cleanker check: clean kept a rust doc comment" >&2
              exit 1
            fi
            printf '#!/usr/bin/env python3\n# Copyright (c) 2026 y0usaf\n"""Module prose."""\n\n\ndef only():\n    """Sole body statement."""\n\n\ndef two():\n    """Doc for two."""\n    return 2\n' > "$tmp/d.py"
            git -C "$tmp" add d.py
            if cleanker hook; then
              echo "cleanker check: gate did not block staged python docstrings" >&2
              exit 1
            fi
            cleanker clean > /dev/null
            git -C "$tmp" add -A
            head -1 "$tmp/d.py" | grep -qx '#!/usr/bin/env python3'
            grep -qx '# Copyright (c) 2026 y0usaf' "$tmp/d.py"
            grep -qx '    pass' "$tmp/d.py"
            grep -qx '    return 2' "$tmp/d.py"
            if grep -q '"""' "$tmp/d.py"; then
              echo "cleanker check: clean kept python docstrings" >&2
              exit 1
            fi
            ${pkgs.python3}/bin/python3 -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "$tmp/d.py"
            cleanker hook
            printf '/**\n * Prose only JSDoc.\n */\nconst a = 1;\n' > "$tmp/e.js"
            git -C "$tmp" add e.js
            if cleanker hook; then
              echo "cleanker check: gate did not block a staged prose JSDoc" >&2
              exit 1
            fi
            cleanker clean > /dev/null
            git -C "$tmp" add -A
            grep -qx 'const a = 1;' "$tmp/e.js"
            if grep -q 'Prose only JSDoc' "$tmp/e.js"; then
              echo "cleanker check: clean kept a prose JSDoc" >&2
              exit 1
            fi
            printf '/**\n * Adds one.\n * @param {number} n\n * @returns {number}\n */\nfunction add(n) { return n + 1; }\n' > "$tmp/f.js"
            printf '/**\n * This program is free software; you can redistribute it.\n * Licensed under the GNU General Public License v3.\n */\nint x;\n' > "$tmp/g.c"
            git -C "$tmp" add f.js g.c
            cleanker hook
            cleanker clean > /dev/null
            grep -q '@param {number} n' "$tmp/f.js"
            grep -q '@returns {number}' "$tmp/f.js"
            grep -q 'Licensed under the GNU General Public License v3' "$tmp/g.c"
            grep -qx 'int x;' "$tmp/g.c"
            cleanker status > /dev/null
            mkdir -p "$tmp/ts/tests" "$tmp/ts/src" "$tmp/ts/demo"
            git -C "$tmp/ts" init -q
            git -C "$tmp/ts" config user.email test@example.com
            git -C "$tmp/ts" config user.name test
            git -C "$tmp/ts" config --local cleanker.policy true
            printf 'name = "demo"\nversion = "0.1.0"\n' > "$tmp/ts/pyproject.toml"
            printf 'import subprocess\n\n\ndef add(a, b):\n    return a + b\n\n\ndef double(x):\n    return add(x, x)\n\n\ndef run_cli():\n    return subprocess.run(["true"], check=False).returncode\n\n\ndef exercise():\n    return run_cli()\n' > "$tmp/ts/demo/__init__.py"
            printf 'import subprocess\n\n\ndef test_cli():\n    subprocess.run(["true"], check=True)\n' > "$tmp/ts/tests/test_cli.py"
            printf 'pub fn add(a: i32, b: i32) -> i32 { a + b }\n\npub fn double(x: i32) -> i32 { add(x, x) }\n\npub fn run_cli() -> bool {\n    std::process::Command::new("true").status().unwrap().success()\n}\n\npub fn exercise() -> bool { run_cli() }\n\npub struct Runner;\n\nimpl Runner {\n    pub fn go(&self) -> bool { run_cli() }\n}\n\n#[cfg(test)]\nmod add_tests {\n    #[test]\n    fn adds() { assert_eq!(super::add(1, 1), 2); }\n}\n\n#[cfg(test)]\nmod double_tests {\n    #[test]\n    fn doubles() { assert_eq!(super::double(2), 4); }\n}\n\n#[cfg(test)]\nmod chain_tests {\n    #[test]\n    fn chains() { super::exercise(); }\n}\n\n#[cfg(test)]\nmod method_tests {\n    #[test]\n    fn via_method() { let r = Runner; r.go(); }\n}\n\n#[cfg(test)]\nmod crate_tests {\n    #[test]\n    fn via_crate() { crate::exercise(); }\n}\n' > "$tmp/ts/src/lib.rs"
            printf 'pub fn run() {\n    std::process::Command::new("true").status().unwrap();\n}\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn spawns() { super::run(); }\n}\n' > "$tmp/ts/src/spawn.rs"
            git -C "$tmp/ts" add -A
            git -C "$tmp/ts" -c core.hooksPath=/dev/null commit -qm init
            printf 'from demo import add\n\n\ndef test_unit():\n    assert add(1, 2) == 3\n' > "$tmp/ts/tests/test_unit.py"
            printf 'from demo import double\n\n\ndef test_double():\n    assert double(2) == 4\n' > "$tmp/ts/tests/test_double.py"
            printf 'from demo import exercise\n\n\ndef test_chain():\n    assert exercise() == 0\n' > "$tmp/ts/tests/test_chain.py"
            cleanker clean "$tmp/ts" > /dev/null
            test -f "$tmp/ts/tests/test_unit.py"
            test -f "$tmp/ts/tests/test_double.py"
            test -f "$tmp/ts/tests/test_chain.py"
            test -f "$tmp/ts/tests/test_cli.py"
            git -C "$tmp/ts" config --local cleanker.strip-tests true
            if cleanker dry-run --check "$tmp/ts" > /dev/null; then
              echo "cleanker check: --check did not report pending test removal" >&2
              exit 1
            fi
            git -C "$tmp/ts" add tests/test_unit.py
            if (cd "$tmp/ts" && ${pkgs.python3}/bin/python3 $src/cleanker.py hook); then
              echo "cleanker check: gate did not block a staged unit test" >&2
              exit 1
            fi
            git -C "$tmp/ts" reset -q tests/test_unit.py
            cleanker clean "$tmp/ts" > /dev/null
            test ! -f "$tmp/ts/tests/test_unit.py"
            test ! -f "$tmp/ts/tests/test_double.py"
            test -f "$tmp/ts/tests/test_chain.py"
            test -f "$tmp/ts/tests/test_cli.py"
            grep -q 'pub fn add' "$tmp/ts/src/lib.rs"
            if grep -q 'add_tests\|double_tests' "$tmp/ts/src/lib.rs"; then
              echo "cleanker check: unit test block survived" >&2
              exit 1
            fi
            for kept in chain_tests method_tests crate_tests; do
              if ! grep -q "$kept" "$tmp/ts/src/lib.rs"; then
                echo "cleanker check: kept test block $kept was removed" >&2
                exit 1
              fi
            done
            grep -q 'cfg(test)' "$tmp/ts/src/spawn.rs"
            ${pkgs.python3}/bin/python3 -m py_compile "$tmp/ts/tests/test_cli.py" "$tmp/ts/tests/test_chain.py" "$tmp/ts/demo/__init__.py"
            cat <<'EOF' > "$tmp/h.css"
        /* c */
        body {}
        EOF
            cat <<'EOF' > "$tmp/h.js"
        // j
        const j = 1;
        EOF
            cat <<'EOF' > "$tmp/h.html"
        <!-- c -->
        <script>// js
        var a = 1;</script>
        <style>/* css */</style>
        EOF
            cat <<'EOF' > "$tmp/h.tsx"
        const a = <div>{/* @ts-ignore */ /* drop */}</div>;
        const b = <div>{/* drop */}</div>;
        EOF
            cat <<'EOF' > "$tmp/h.py"
        def f(): """doc"""  # noqa
        def g(): """doc"""; return 1
        def h():
            """a
            b"""  # noqa
        EOF
            cat <<'EOF' > "$tmp/h.swift"
        // s1
        /* s2 */
        let s = 1
        EOF
            cat <<'EOF' > "$tmp/h.kt"
        // k1
        /* k2 */
        val k = 1
        EOF
            git -C "$tmp" add h.css h.js h.html h.tsx h.py h.swift h.kt
            cleanker clean "$tmp" > /dev/null
            grep -q '</style>' "$tmp/h.html"
            grep -q '</script>' "$tmp/h.html"
            grep -q '@ts-ignore' "$tmp/h.tsx"
            if grep -q 'drop' "$tmp/h.tsx"; then
              echo "cleanker check: drop comment survived in tsx" >&2
              exit 1
            fi
            grep -q 'def f(): pass  # noqa' "$tmp/h.py"
            grep -q 'return 1' "$tmp/h.py"
            grep -q '# noqa' "$tmp/h.py"
            ${pkgs.python3}/bin/python3 -m py_compile "$tmp/h.py"
            if grep -q 's2\|k2' "$tmp/h.swift" "$tmp/h.kt"; then
              echo "cleanker check: swift or kotlin block comment survived" >&2
              exit 1
            fi
            cat <<'EOF' >> "$tmp/ts/demo/__init__.py"
        def get(x):
            return x
        EOF
            cat <<'EOF' > "$tmp/ts/tests/test_http.py"
        from demo import get
        import httpx

        def test_http():
            assert httpx.get("https://example.com").status_code == 200
        EOF
            cat <<'EOF' > "$tmp/ts/tests/test_store.py"
    from demo import add

    def test_store(redis_client):
        assert redis_client.keys() == [b"x"]
    EOF
            cat <<'EOF' > "$tmp/ts/tests/test_fs.py"
        import os
        from demo import add

        def test_fs():
            with open("/tmp/x", "w") as fh:
                fh.write("hi")
            os.remove("/tmp/x")
            assert add(1, 1) == 2
        EOF
            cat <<'EOF' >> "$tmp/ts/src/lib.rs"
        #[cfg(test)]
        mod esc_tests {
            #[test]
            fn esc() { let _c = '\"'; assert_eq!(super::add(1, 1), 2); }
        }

        pub fn kept_after() -> i32 { 2 }
        EOF
            git -C "$tmp/ts" add -A
            cleanker clean "$tmp/ts" > /dev/null
            test -f "$tmp/ts/tests/test_http.py"
            test -f "$tmp/ts/tests/test_fs.py"
            test -f "$tmp/ts/tests/test_store.py"
            grep -q 'pub fn kept_after' "$tmp/ts/src/lib.rs"
            if grep -q 'esc_tests' "$tmp/ts/src/lib.rs"; then
              echo "cleanker check: esc_tests survived" >&2
              exit 1
            fi
            mkdir -p "$tmp/ts/ignored"
            printf 'ignored/\n' > "$tmp/ts/.cleankerignore"
            printf '# keep ignored\nx = 1\n' > "$tmp/ts/ignored/gen.py"
            printf 'import subprocess\n\ndef helper():\n    subprocess.run(["true"], check=False)\n' > "$tmp/ts/src/other.py"
            printf 'def helper():\n    return 1\n\ndef test_local():\n    assert helper() == 1\n' > "$tmp/ts/src/mod.py"
            git -C "$tmp/ts" add .cleankerignore ignored/gen.py src/other.py src/mod.py
            cleanker clean "$tmp/ts" > /dev/null
            grep -qx '# keep ignored' "$tmp/ts/ignored/gen.py"
            if grep -q 'test_local' "$tmp/ts/src/mod.py"; then
              echo "cleanker check: clean failed to resolve local helper in strip_test_blocks" >&2
              exit 1
            fi
            mkdir -p "$tmp/push"
            git -C "$tmp/push" init -q
            git -C "$tmp/push" config user.email test@example.com
            git -C "$tmp/push" config user.name test
            git -C "$tmp/push" config --local cleanker.policy true
            printf 'x = 1\n' > "$tmp/push/a.py"
            git -C "$tmp/push" add a.py
            git -C "$tmp/push" -c core.hooksPath=/dev/null commit -qm clean
            clean_sha=$(git -C "$tmp/push" rev-parse HEAD)
            printf '# dirty working tree\nx = 1\n' > "$tmp/push/a.py"
            if ! (cd "$tmp/push" && printf 'refs/heads/main %s refs/heads/main 0000000000000000000000000000000000000000\n' "$clean_sha" | ${pkgs.python3}/bin/python3 "$src/cleanker.py" pre-push); then
              echo "cleanker check: pre-push blocked clean commit due to dirty working tree" >&2
              exit 1
            fi
            git -C "$tmp/push" add a.py
            git -C "$tmp/push" -c core.hooksPath=/dev/null commit -qm dirty
            dirty_sha=$(git -C "$tmp/push" rev-parse HEAD)
            printf 'x = 1\n' > "$tmp/push/a.py"
            if (cd "$tmp/push" && printf 'refs/heads/main %s refs/heads/main %s\n' "$dirty_sha" "$clean_sha" | ${pkgs.python3}/bin/python3 "$src/cleanker.py" pre-push); then
              echo "cleanker check: pre-push allowed dirty commit due to clean working tree" >&2
              exit 1
            fi
            mkdir -p "$tmp/bin" "$tmp/ext"
            printf '#!/bin/sh\nexec %s/bin/python3 %s/cleanker.py "$@"\n' "${pkgs.python3}" "$src" > "$tmp/bin/cleanker"
            chmod +x "$tmp/bin/cleanker"
            git -C "$tmp/ext" init -q
            git -C "$tmp/ext" config user.email test@example.com
            git -C "$tmp/ext" config user.name test
            git -C "$tmp/ext" config --local cleanker.policy true
            printf '# pre-existing comment\nx = 1\n' > "$tmp/ext/dirty.py"
            printf '# keep me\nz = 3\n' > "$tmp/ext/read_only.py"
            git -C "$tmp/ext" add -A
            git -C "$tmp/ext" -c core.hooksPath=/dev/null commit -qm init
            printf '# modified unrelated\nx = 1\n' > "$tmp/ext/dirty.py"
            for ext_file in "$src/omp-cleanker/omp-extension.ts" "$src/pi-cleanker/pi-extension.ts"; do
              printf '# agent comment\ny = 2\n' > "$tmp/ext/agent.py"
              PATH="$tmp/bin:$PATH" ${pkgs.nodejs}/bin/node --input-type=module -e '
                import fs from "node:fs";
                import path from "node:path";
                const mod = (await import(process.argv[1])).default;
                const cwd = process.argv[2];
                const handlers = new Map();
                const cmds = new Map();
                const notes = [];
                mod({
                  registerCommand(name, def) { cmds.set(name, def); },
                  on(ev, fn) { handlers.set(ev, fn); },
                });
                const ctx = { cwd, ui: { notify(msg, level) { notes.push({ msg, level }); } } };
                await handlers.get("tool_result")({ toolName: "read", input: { path: "read_only.py" }, isError: false }, ctx);
                if (!fs.readFileSync(path.join(cwd, "read_only.py"), "utf8").includes("# keep me")) {
                  throw new Error("read tool_result modified read_only.py");
                }
                await handlers.get("tool_result")({ toolName: "write", input: { path: "agent.py" }, isError: false }, ctx);
                if (fs.readFileSync(path.join(cwd, "agent.py"), "utf8").trim() !== "y = 2") {
                  throw new Error("write tool_result did not clean agent.py");
                }
                fs.writeFileSync(path.join(cwd, "agent.py"), "# later comment\ny = 2\n");
                await handlers.get("agent_end")({}, ctx);
                if (fs.readFileSync(path.join(cwd, "agent.py"), "utf8").trim() !== "y = 2") {
                  throw new Error("agent_end did not clean session-touched agent.py");
                }
                if (!fs.readFileSync(path.join(cwd, "dirty.py"), "utf8").includes("# modified unrelated")) {
                  throw new Error("agent_end modified unrelated dirty.py");
                }
                await handlers.get("agent_end")({}, ctx);
                if (!fs.readFileSync(path.join(cwd, "dirty.py"), "utf8").includes("# modified unrelated")) {
                  throw new Error("empty agent_end modified unrelated dirty.py");
                }
                await cmds.get("cleanker").handler("dry-run --strip-tests", ctx);
                if (!notes.some((n) => n.level === "info")) {
                  throw new Error("cleanker command failed to split flags");
                }
              ' "$ext_file" "$tmp/ext"
            done
  '';
  installPhase = ''
    install -Dm755 $src/cleanker.py $out/libexec/cleanker.py
    mkdir -p $out/bin $out/share/git-hooks
    makeWrapper ${pkgs.python3}/bin/python3 $out/bin/cleanker \
      --add-flags $out/libexec/cleanker.py \
      --prefix PATH : ${pkgs.lib.makeBinPath [pkgs.ast-grep]}
    printf '#!/bin/sh\nexec %s/bin/cleanker hook\n' "$out" > $out/share/git-hooks/pre-commit
    printf '#!/bin/sh\nexec %s/bin/cleanker pre-push\n' "$out" > $out/share/git-hooks/pre-push
    chmod +x $out/share/git-hooks/pre-commit $out/share/git-hooks/pre-push
  '';
}
