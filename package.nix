{pkgs}:
pkgs.stdenv.mkDerivation {
  pname = "cleanker";
  version = "1";
  src = ./.;
  nativeBuildInputs = [pkgs.makeWrapper];
  nativeCheckInputs = [pkgs.git pkgs.ast-grep];
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
    printf 'def add(a, b):\n    return a + b\n' > "$tmp/ts/demo/__init__.py"
    printf 'import subprocess\n\n\ndef test_cli():\n    subprocess.run(["true"], check=True)\n' > "$tmp/ts/tests/test_cli.py"
    printf 'pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn adds() { assert_eq!(super::add(1, 1), 2); }\n}\n' > "$tmp/ts/src/lib.rs"
    printf 'pub fn run() {\n    std::process::Command::new("true").status().unwrap();\n}\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn spawns() { super::run(); }\n}\n' > "$tmp/ts/src/spawn.rs"
    git -C "$tmp/ts" add -A
    git -C "$tmp/ts" -c core.hooksPath=/dev/null commit -qm init
    printf 'from demo import add\n\n\ndef test_unit():\n    assert add(1, 2) == 3\n' > "$tmp/ts/tests/test_unit.py"
    cleanker clean "$tmp/ts" > /dev/null
    test -f "$tmp/ts/tests/test_unit.py"
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
    test -f "$tmp/ts/tests/test_cli.py"
    grep -q 'pub fn add' "$tmp/ts/src/lib.rs"
    if grep -q 'cfg(test)' "$tmp/ts/src/lib.rs"; then
      echo "cleanker check: unit test block survived" >&2
      exit 1
    fi
    grep -q 'cfg(test)' "$tmp/ts/src/spawn.rs"
    ${pkgs.python3}/bin/python3 -m py_compile "$tmp/ts/tests/test_cli.py" "$tmp/ts/demo/__init__.py"
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
