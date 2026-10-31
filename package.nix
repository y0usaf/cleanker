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
    if (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py hook); then
      echo "cleanker check: gate did not block a staged python comment" >&2
      exit 1
    fi
    (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py clean > /dev/null)
    grep -qx 'x = 1' "$tmp/a.py"
    git -C "$tmp" add a.py
    (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py hook)
    printf '// bad\nfn main() {}\n' > "$tmp/a.rs"
    git -C "$tmp" add a.rs
    if (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py hook); then
      echo "cleanker check: gate did not block a staged rust comment" >&2
      exit 1
    fi
    (cd "$tmp" && ${pkgs.python3}/bin/python3 $src/cleanker.py status > /dev/null)
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
