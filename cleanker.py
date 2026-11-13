#!/usr/bin/env python3
import argparse, ast, bisect, collections, fnmatch, functools, json, os, re, shutil, subprocess, sys, tempfile

SKIP_DIRS = {".git","node_modules","target","dist","build","result",".direnv","vendor","ref","corpus",
             "third_party","uv-cache",".venv","venv",".cache",".dioxus","engine-reference","subprojects"}
OWN_OWNERS = {"y0usaf","sylvarant-ai","Inscendai","thepresciencecompany","shodown96"}
LANG_OF_EXT = {"py":"Python","pyi":"Python","rs":"Rust","ts":"TypeScript","tsx":"Tsx","js":"JavaScript",
  "jsx":"JavaScript","mjs":"JavaScript","cjs":"JavaScript","go":"Go","nix":"Nix","lua":"Lua","c":"C","h":"C",
  "cpp":"Cpp","cc":"Cpp","hpp":"Cpp","cxx":"Cpp","cs":"CSharp","zig":"Zig","sh":"Bash","bash":"Bash","rb":"Ruby",
  "swift":"Swift","kt":"Kotlin","scala":"Scala","ex":"Elixir","exs":"Elixir","hs":"Haskell","php":"Php","dart":"Dart",
  "css":"Css","html":"Html","htm":"Html","yml":"Yaml","yaml":"Yaml"}
KINDS = {"Rust":["line_comment","block_comment"],"Java":["line_comment","block_comment"],
         "Kotlin":["line_comment"],"Scala":["comment","block_comment"],"Dart":["comment","block_comment"]}
DIRECTIVE = [
  r"^#!", r"^//go:", r"^//\+build", r"^#\s*type:", r"^#\s*noqa", r"^#\s*fmt:", r"^#\s*isort:",
  r"^#\s*pyright:", r"^#\s*mypy:", r"coding[:=]", r"^#\s*pylint:", r"^#\s*pragma:",
  r"@ts-expect-error", r"@ts-ignore", r"@ts-nocheck", r"@ts-check", r"eslint", r"biome-ignore",
  r"prettier-ignore", r"@__PURE__", r"///\s*<reference", r"SPDX-License-Identifier", r"shellcheck",
  r"^#\s*strictix:", r"nolint", r"no cover", r"@jsxImportSource", r"@jsxRuntime",
  r"^//\s*SAFETY", r"^---@", r"istanbul ignore", r"c8 ignore", r"v8 ignore", r"jscpd:ignore",
  r"noinspection", r"@flow", r"fallthrough", r"^//\s*@vitest-environment", r"rome-ignore",
  r"@vite-ignore", r"webpackIgnore", r"turbopackIgnore", r"webpackChunkName", r"webpackMode",
  r"@jest-environment", r"Copyright \(c\)", r"Copyright \d{4}", r"Permission is hereby granted",
  r"Apache License", r"MIT License", r"Licensed under", r"@generated", r"DO NOT EDIT",
  r"^#\s*renovate:", r"^#\s*yamllint", r"^#\s*yaml-language-server", r"^#\s*editorconfig",
  r"<!--\s*prettier-", r"<!--\s*markdownlint", r"<!--\s*htmlhint", r"<!--\s*cspell",
  r"<!--#include", r"<!--\s*keep", r"^//\s*==/?UserScript==",
  r"@(?:type|typedef|template|satisfies|callback|enum|import|overload)\b", r"@(?:param|returns?)\s*\{",
  r"^//\s*@(name|namespace|version|description|author|license|match|exclude-match|include|exclude|grant|connect|require|resource|icon|run-at|noframes|inject-into|sandbox|unwrap|downloadURL|updateURL|homepageURL|supportURL)(:[\w-]+)?(\s|$)",
]
KEEP_MD = [r"^README(\.|$)", r"^README$", r"^AGENTS\.md$"]
LEGAL_MD = [r"^LICEN[CS]E", r"^NOTICE", r"^PROVENANCE", r"^THIRD_PARTY"]
_ag = None
def ag():
    global _ag
    if _ag and os.path.exists(_ag): return _ag
    found = shutil.which("ast-grep")
    if found:
        _ag = found; return _ag
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ast-grep")
    link = os.path.join(os.path.dirname(cache), "ast-grep-root")
    if os.path.exists(cache):
        path = open(cache).read().strip()
        if os.path.exists(path): _ag = path; return _ag
    subprocess.run(["nix","build","--out-link",link,"nixpkgs#ast-grep"], capture_output=True)
    path = os.path.join(link, "bin", "ast-grep")
    if not os.path.exists(path):
        raise SystemExit("cleanker: ast-grep not found on PATH and nixpkgs#ast-grep would not build")
    open(cache,"w").write(path)
    _ag = path
    return _ag

def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)

def git(repo, *args):
    return sh(["git","-C",repo,*args])

def repo_root(gitdir):
    return os.path.dirname(gitdir)

def common_dir(repo):
    p = git(repo,"rev-parse","--path-format=absolute","--git-common-dir")
    return p.stdout.strip() or repo

def discover(root):
    gitdirs = [x for x in sh(["find",root,"-maxdepth","6","-name",".git","-not","-path","*/.git/*","-print0"]).stdout.split("\0") if x]
    groups = {}
    for g in gitdirs:
        d = repo_root(g)
        if any(part in SKIP_DIRS for part in d.split(os.sep)): continue
        rel = os.path.relpath(d, root)
        if any(part.startswith(".") for part in rel.split(os.sep)): continue
        groups.setdefault(common_dir(d), []).append((d, rel))
    repos = []
    for cd, members in groups.items():
        members.sort(key=lambda x: (os.path.isdir(os.path.join(x[0], ".git")) is False,
                                    x[1].startswith("sandbox/"), len(x[1])))
        d, rel = members[0]
        remote = git(d,"remote","get-url","origin").stdout.strip()
        m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", remote)
        owner = m.group(1) if m else ""
        repos.append({"path":d,"common":cd,"remote":remote,"owner":owner,
                      "clones":[x[0] for x in members[1:]],
                      "zone": rel.split(os.sep)[0],
                      "owned": owner in OWN_OWNERS or (owner == "" and rel.split(os.sep)[0] in {"developing","maintaining"})})
    return repos

def tracked(repo):
    p = git(repo,"ls-files","-z","--cached","--others","--exclude-standard")
    return [f for f in p.stdout.split("\0") if f]

def lang_files(repo):
    out = collections.defaultdict(list)
    for rel in tracked(repo):
        if any(part in SKIP_DIRS for part in rel.split("/")): continue
        e = rel.rsplit(".",1)[-1].lower() if "." in os.path.basename(rel) else ""
        l = LANG_OF_EXT.get(e)
        if l: out[l].append(os.path.join(repo,rel))
    return out

def rule(lang, kinds=None, inside=None):
    ks = kinds or KINDS.get(lang,["comment"])
    body = "  any:\n" + "".join("    - kind: %s\n" % k for k in ks)
    if inside:
        body = "  all:\n    - kind: %s\n    - inside:\n        kind: %s\n        stopBy: end\n" % (ks[0], inside)
    return "id: c\nlanguage: %s\nrule:\n%s" % (lang, body)

def chunks(files, limit=800, budget=400_000):
    batch, size = [], 0
    for f in files:
        if batch and (len(batch) >= limit or size + len(f) > budget):
            yield batch; batch, size = [], 0
        batch.append(f); size += len(f) + 1
    if batch: yield batch

def scan(files, lang, kinds=None, inside=None):
    if not files: return []
    out = []
    for part in chunks(files):
        out.extend(scan_chunk(part, lang, kinds, inside))
    return out

def scan_chunk(files, lang, kinds=None, inside=None):
    p = sh([ag(),"scan","--inline-rules",rule(lang,kinds,inside),"--json=stream",*files])
    if p.returncode != 0 and not p.stdout.strip():
        print("cleanker: ast-grep failed for %s (%s)" % (lang, (p.stderr or "").strip().splitlines()[:1]), file=sys.stderr)
    out = []
    for line in p.stdout.splitlines():
        if '"ruleId"' in line:
            try: out.append(json.loads(line))
            except ValueError: pass
    return out

def scan_rule(files, rules):
    out = []
    for part in chunks(files):
        p = sh([ag(),"scan","--inline-rules",rules,"--json=stream",*part])
        for line in p.stdout.splitlines():
            if '"ruleId"' in line:
                try: out.append(json.loads(line))
                except ValueError: pass
    return out

PY_DOC = "id: d_Python\nlanguage: Python\nrule:\n  kind: expression_statement\n  has:\n    kind: string\n    stopBy: end\n"

def scan_all(by_lang):
    langs = [k for k, v in by_lang.items() if v]
    out = collections.defaultdict(list)
    errs = collections.Counter()
    containers = collections.defaultdict(list)
    if not langs: return out, errs, containers
    rules, files = [], []
    for lang in langs:
        ks = KINDS.get(lang, ["comment"])
        rules.append("id: c_%s\nlanguage: %s\nrule:\n  any:\n%s" % (lang, lang, "".join("    - kind: %s\n" % k for k in ks)))
        rules.append("id: e_%s\nlanguage: %s\nrule:\n  kind: ERROR\n" % (lang, lang))
        if lang == "Tsx":
            rules.append("id: j_%s\nlanguage: %s\nrule:\n  kind: jsx_expression\n" % (lang, lang))
        if lang == "Python":
            rules.append(PY_DOC)
        files.extend(by_lang[lang])
    p = sh([ag(),"scan","--inline-rules","\n---\n".join(rules),"--json=stream",*files])
    if p.returncode != 0 and not p.stdout.strip():
        for lang in langs:
            for n in scan(by_lang[lang], lang): out[n["file"]].append(n)
            for n in scan(by_lang[lang], lang, ["ERROR"]): errs[n["file"]] += 1
            if lang == "Tsx":
                for c in scan(by_lang[lang], lang, ["jsx_expression"]): containers[c["file"]].append(c)
            if lang == "Python":
                for n in scan_rule(by_lang[lang], PY_DOC): n["doc"] = True; out[n["file"]].append(n)
    else:
        for line in p.stdout.splitlines():
            if '"ruleId"' not in line: continue
            try: n = json.loads(line)
            except ValueError: continue
            rid = n["ruleId"]
            if rid.startswith("e_"): errs[n["file"]] += 1
            elif rid.startswith("j_"): containers[n["file"]].append(n)
            elif rid.startswith("d_"): n["doc"] = True; out[n["file"]].append(n)
            else: out[n["file"]].append(n)
    for lang in langs:
        for n in embedded(by_lang[lang], lang): out[n["file"]].append(n)
    cand = {n["file"] for ns in out.values() for n in ns if n.get("doc")}
    docs = py_docs(cand)
    for f, ns in out.items():
        if f not in cand: continue
        table = docs.get(f, {})
        keep = []
        for n in ns:
            if not n.get("doc"):
                keep.append(n); continue
            at = n["range"]["byteOffset"]["start"]
            if at not in table: continue
            n["replace"] = table[at]; keep.append(n)
        out[f] = keep
    return out, errs, containers

def py_docs(files):
    out = {}
    for f in files:
        try:
            with open(f, "rb") as fh: data = fh.read()
            tree = ast.parse(data)
        except (OSError, SyntaxError, ValueError):
            continue
        starts, off, table = [0], 0, {}
        for line in data.split(b"\n"):
            off += len(line) + 1; starts.append(off)
        stack = [tree]
        while stack:
            n = stack.pop()
            if not isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)): continue
            stack.extend(ast.iter_child_nodes(n))
            if not n.body: continue
            d = n.body[0]
            if not (isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str)): continue
            table[starts[d.lineno - 1] + d.col_offset] = "pass" if len(n.body) == 1 else ""
        if table: out[f] = table
    return out

EMBED = {"Html": [("JavaScript","script_element","js"), ("Css","style_element","css")]}

def embedded(files, lang):
    out = []
    for sub, host, ext in EMBED.get(lang, []):
        hosts = scan(files, lang, ["raw_text"], inside=host)
        for h in hosts:
            data = h["text"].encode()
            fd, tmp = tempfile.mkstemp(suffix="." + ext)
            os.close(fd)
            with open(tmp,"wb") as fh: fh.write(data)
            base = h["range"]["byteOffset"]["start"]
            for n in scan([tmp], sub):
                out.append({"file": h["file"], "text": n["text"],
                            "range": {"byteOffset": {"start": base + n["range"]["byteOffset"]["start"],
                                                     "end": base + n["range"]["byteOffset"]["end"]},
                                      "start": {"line": 0}, "end": {"line": 0}}})
            os.unlink(tmp)
    return out

KEEP_RE = re.compile("|".join("(?:%s)" % p for p in DIRECTIVE), re.M)

@functools.lru_cache(maxsize=8192)
def classified(text):
    if KEEP_RE.search(text.strip()): return "keep"
    return "drop"

def md_policy(rel):
    base = rel.rsplit("/",1)[-1]
    for p in KEEP_MD:
        if re.search(p, base): return "keep"
    for p in LEGAL_MD:
        if re.search(p, base): return "legal"
    return "drop"

def strip_src(src, nodes, containers=()):
    data = src.encode()
    lines = data.split(b"\n")
    starts, off = [], 0
    for l in lines:
        starts.append(off); off += len(l) + 1
    def span(s, e):
        return bisect.bisect_right(starts, s) - 1, bisect.bisect_right(starts, e) - 1
    def line_end(k):
        return starts[k] + len(lines[k])
    cuts = collections.defaultdict(list)
    dropped = set()
    verdict = {id(n): classified(n["text"]) for n in nodes}
    kept = [(n["range"]["byteOffset"]["start"], n["range"]["byteOffset"]["end"])
            for n in nodes if verdict[id(n)] == "keep"]
    drops = [(n["range"]["byteOffset"]["start"], n["range"]["byteOffset"]["end"])
             for n in nodes if verdict[id(n)] == "drop"]
    for n in nodes:
        if verdict[id(n)] == "keep": continue
        s = n["range"]["byteOffset"]["start"]; e = n["range"]["byteOffset"]["end"]
        inner = [c for c in containers
                 if c["range"]["byteOffset"]["start"] <= s and e <= c["range"]["byteOffset"]["end"]]
        if inner:
            c = min(inner, key=lambda k: k["range"]["byteOffset"]["end"] - k["range"]["byteOffset"]["start"])
            cs0, ce0 = c["range"]["byteOffset"]["start"], c["range"]["byteOffset"]["end"]
            inside = data[cs0:ce0]
            for a, b in kept + drops:
                if cs0 <= a and b <= ce0: inside = inside.replace(data[a:b], b"", 1)
            if inside.replace(b"{", b"").replace(b"}", b"").strip() == b"":
                s, e = cs0, ce0
        rep = (n.get("replace") or "").encode()
        i, j = span(s, e)
        if rep:
            cuts[i].append((s - starts[i], len(lines[i]), rep))
            if i < j and data[e:line_end(j)].strip():
                cuts[j].append((0, e - starts[j], b"")); dropped.update(range(i + 1, j))
            else:
                dropped.update(range(i + 1, j + 1))
            continue
        if i == j and data[starts[i]:s].strip() == b"" and data[e:line_end(i)].strip() == b"":
            dropped.add(i); continue
        if i < j and data[starts[i]:s].strip() == b"" and data[e:line_end(j)].strip() == b"":
            dropped.update(range(i, j + 1)); continue
        k = i
        while k <= j:
            lo = s if k == i else starts[k]
            hi = e if k == j else line_end(k)
            if k < j and lo == starts[k] and hi == line_end(k):
                dropped.add(k)
            else:
                cuts[k].append((lo - starts[k], hi - starts[k], b""))
            k += 1
    out, after_drop = [], False
    for i, l in enumerate(lines):
        if i in dropped:
            after_drop = True; continue
        if i in cuts:
            for a, b, rep in sorted(cuts[i], reverse=True):
                a = max(0, a); b = min(len(l), b)
                left = l[:a]; right = l[b:]
                if rep:
                    l = left + rep + right
                elif left.rstrip() and right.lstrip():
                    l = left + b" " + right
                else:
                    l = left + right
            cr = b"\r" if lines[i].endswith(b"\r") else b""
            l = l.rstrip() + cr
        if after_drop and l.strip() == b"" and out and out[-1].strip() == b"":
            after_drop = False; continue
        if l.strip(): after_drop = False
        out.append(l)
    return b"\n".join(out).decode()

BINS = "/tmp/cleanker/bins"
def tool(name, attr):
    os.makedirs(BINS, exist_ok=True)
    cache = os.path.join(BINS, name)
    if not os.path.exists(cache):
        p = subprocess.run(["nix","build","--no-link","--print-out-paths",attr], capture_output=True, text=True)
        if p.returncode != 0: return None
        open(cache,"w").write(p.stdout.strip())
    root = open(cache).read().strip()
    for cand in (os.path.join(root,"bin",name), os.path.join(root,name)):
        if os.path.exists(cand): return cand
    return None

def fmt_cmd(repo, lang, path):
    if lang == "Rust":
        t = tool("rustfmt","nixpkgs#rustfmt")
        return [t,"--edition","2021",path] if t else None
    if lang in {"TypeScript","Tsx","JavaScript"}:
        t = tool("biome","nixpkgs#biome") or shutil.which("biome")
        return [t,"format","--write",path] if t else None
    if lang == "Nix":
        t = tool("nixfmt","nixpkgs#nixfmt")
        return [t,path] if t else None
    if lang == "Python":
        t = tool("ruff","nixpkgs#ruff")
        return [t,"format","--quiet",path] if t else None
    return None

def corpus(top, files):
    parts = []
    for f in files:
        if f.lower().endswith((".md",".mdx")): continue
        if any(x in SKIP_DIRS for x in f.split("/")): continue
        p = os.path.join(top, f)
        try:
            if os.path.islink(p) or os.path.getsize(p) > 2_000_000: continue
            with open(p, "rb") as fh: parts.append(fh.read())
        except OSError: continue
    return b"\n".join(parts)

def refs_in(top, rel, files=None, blob=None):
    base = os.path.basename(rel)
    if blob is not None:
        return ["*"] if (rel.encode() in blob or base.encode() in blob) else []
    hits = []
    for f in (files if files is not None else tracked(top)):
        if f.lower().endswith((".md",".mdx")) or f == rel: continue
        if any(x in SKIP_DIRS for x in f.split("/")): continue
        p = os.path.join(top, f)
        try:
            if os.path.getsize(p) > 2_000_000: continue
            with open(p, "rb") as fh: data = fh.read()
        except OSError: continue
        if rel.encode() in data or base.encode() in data: hits.append(f)
    return hits

def refs_to(repo, rel):
    hits = []
    for f in tracked(repo):
        if f.lower().endswith((".md",".mdx")): continue
        if any(x in SKIP_DIRS for x in f.split("/")): continue
        p = os.path.join(repo, f)
        try:
            if os.path.getsize(p) > 2_000_000: continue
            t = open(p, encoding="utf-8", errors="ignore").read()
        except OSError: continue
        if rel in t or rel.rsplit("/",1)[-1] in t:
            hits.append((f, "exact" if rel in t else "basename"))
    return hits

TESTS_KEY = "cleanker.strip-tests"
TEST_DIR_NAMES = {"test","tests","testing","testdata","test-data","test_data","spec","specs","__tests__","__snapshots__","checks"}
FIXTURE_DIR_NAMES = {"fixtures","fixture","data","snapshots","__snapshots__","testdata","golden","goldens"}
CODE_EXTS = {"py","pyi","rs","go","js","ts","tsx","jsx","mjs","cjs","cs","fs","rb","lua","lisp","el","ex","exs",
             "c","h","cc","cpp","hpp","cxx","hh","sh","bash","zsh","nix","kt","swift","scala","java","php","dart","pl","r"}
DATA_EXTS = {"toml","json","yaml","yml","txt","snap","csv","tsv"}
PROJ_EXTS = {"csproj","fsproj","vbproj","sln","slnx"}
COMMON_BASENAMES = {"mod.rs","lib.rs","main.rs","__init__.py","index.js","index.ts","index.tsx","build.rs",
                    "utils.py","utils.rs","setup.py","common.py","common.rs","helpers.py","helpers.rs","support.py"}
E2E_NAME_RE = re.compile(r"(?:^|[._-])(?:e2e|end[-_]?to[-_]?end|integration|acceptance|functional|smoke|vm|nixos)(?:[._-]|$)", re.I)
TEST_STEM_RE = re.compile(r"^(?:test_.+|[^/]*_test|[^/]*[._-](?:test|spec)|tests?)$", re.I)
TEST_PROJ_RE = re.compile(r"\.(?:tests?|specs?)$", re.I)
EXT_LANG = {"jsx":"js","ts":"js","tsx":"js","mjs":"js","cjs":"js","bash":"sh","zsh":"sh","pyi":"py","fs":"cs"}
SPAWN = {
  "py": r"subprocess\.|os\.system\(|os\.exec[lv]p?e?|pexpect|pty\.spawn|requests\.(?:get|post|put|delete|patch|request)|urllib\.request|http\.client|http\.server|socket\.|socketserver|HTTPServer|BaseHTTPRequestHandler|uvicorn|gunicorn|flask|FastAPI|TestClient|playwright|selenium|docker|podman|qemu",
  "rs": r"std::process::Command|process::Command|assert_cmd|Command::cargo_bin|CARGO_BIN_EXE_|escargot|duct::|reqwest|TcpStream|TcpListener|UnixListener|UdpSocket|hyper::|docker|podman|qemu",
  "go": r"os/exec|exec\.Command|httptest\.NewServer|http\.(?:Get|Post|Client|ListenAndServe)|net\.Listen|docker|podman|qemu",
  "js": r"child_process|execa\(|spawnSync\(|(?<![.\w])spawn\(|supertest|playwright|cypress|puppeteer|fetch\(|axios|createServer|listen\(",
  "cs": r"Process\.Start|ProcessStartInfo|HttpClient|WebApplicationFactory|HttpListener|TcpListener|Kestrel|Docker",
  "lisp": r"run-program|launch-program|uiop:|sb-bsd-sockets|usocket|hunchentoot",
  "nix": r"runNixOSTest|nixosTest|nixos/lib/testing",
  "zig": r"std\.process|ChildProcess|execv",
  "sh": r"(?s).",
}

def tests_on(repo, override=False):
    return bool(override) or setting(repo, TESTS_KEY).strip().lower() in {"true","1","yes","on"}

def ext_of(rel):
    base = rel.rsplit("/",1)[-1]
    return base.rsplit(".",1)[-1].lower() if "." in base else ""

def stem_of(rel):
    base = rel.rsplit("/",1)[-1]
    return base.rsplit(".",1)[0] if "." in base else base

def test_stem(stem):
    return bool(TEST_STEM_RE.match(stem) or re.match(r"^[A-Za-z0-9_.-]*Tests?$", stem))

def test_candidate(rel):
    e = ext_of(rel)
    stem = stem_of(rel)
    if e in PROJ_EXTS: return False
    if e not in CODE_EXTS and e not in DATA_EXTS: return False
    deep = rel.split("/")[:-1]
    for k, seg in enumerate(deep):
        if seg.lower() not in TEST_DIR_NAMES and not TEST_PROJ_RE.search(seg): continue
        if any(s.lower() in FIXTURE_DIR_NAMES for s in deep[k+1:]): return True
    if e == "rs" and deep and deep[-1].lower() == "tests": return True
    if e in CODE_EXTS and deep and (deep[-1].lower() in TEST_DIR_NAMES or TEST_PROJ_RE.search(deep[-1])): return True
    if e in CODE_EXTS and any(seg.lower() == "__tests__" for seg in deep): return True
    return bool(e in CODE_EXTS and test_stem(stem))

def e2e_named(rel):
    if any(E2E_NAME_RE.search(seg) for seg in rel.split("/")[:-1]): return "end-to-end path"
    return "end-to-end name" if E2E_NAME_RE.search(stem_of(rel)) else ""

def spawn_hit(rel, text):
    e = ext_of(rel)
    pat = SPAWN.get(EXT_LANG.get(e, e))
    if not pat: return ""
    if re.search(pat, text, re.I):
        return "spawns a process or a server"
    return ""

def project_names(repo):
    names = set()
    for rel in tracked(repo):
        base = rel.rsplit("/",1)[-1]
        if base not in {"Cargo.toml","pyproject.toml","package.json"} and not base.endswith((".csproj",".fsproj")):
            continue
        try: text = open(os.path.join(repo, rel), encoding="utf-8", errors="ignore").read()
        except OSError: continue
        m = None
        if base == "Cargo.toml":
            m = re.search(r'(?ms)^\[package\].*?^name\s*=\s*"([^"]+)"', text)
        elif base == "pyproject.toml":
            m = re.search(r'(?m)^name\s*=\s*"([^"]+)"', text)
        elif base == "package.json":
            m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
        else:
            m = re.search(r"<(?:RootNamespace|AssemblyName)>([^<]+)<", text)
        if m:
            names.add(m.group(1))
            names.add(m.group(1).rsplit("/",1)[-1].replace("-", "_"))
    for rel in tracked(repo):
        parts = rel.split("/")
        if parts[-1] == "__init__.py" and len(parts) > 1: names.add(parts[-2])
        if parts[0] == "src" and len(parts) > 2: names.add(parts[1])
        if rel.endswith(".py") and len(parts[-1]) > 4:
            stem = parts[-1][:-3]
            if stem not in {"__init__", "conftest", "setup"} and not test_stem(stem): names.add(stem)
    return {n for n in names if len(n) > 1}

def internal_ref(rel, text, names):
    e = ext_of(rel)
    if e == "rs":
        if re.search(r"\buse\s+(?:crate|super|self)::", text) or re.search(r"\bmod\s+\w+\s*;", text): return True
        return any(re.search(r"\b(?:use|extern\s+crate)\s+%s\b" % re.escape(n), text) for n in names)
    if e == "py":
        if re.search(r"\bfrom\s+\.\s*import\b|\bfrom\s+\.\w+\s+import\b", text): return True
        return any(re.search(r"(?m)^\s*(?:from\s+%s(?:\.|\s+import)|import\s+%s(?:\.|\s|$))" % (re.escape(n), re.escape(n)), text) for n in names)
    if e == "go":
        return bool(re.search(r"(?m)^package\s+\w+", text))
    if e in {"js","ts","tsx","jsx","mjs","cjs"}:
        if re.search(r"""(?:from|require\()\s*["']\.{1,2}/""", text): return True
        return any(re.search(r"""(?:from|require\()\s*["'](?:%s)(?:["'/])""" % re.escape(n), text) for n in names)
    if e in {"cs","fs"}:
        return any(re.search(r"\busing\s+%s\b" % re.escape(n), text) for n in names)
    if e in {"lisp","el","clj"}:
        return bool(re.search(r"\(in-package|\(defpackage|load-system|quickload|\brequire\b", text))
    if e == "zig":
        return bool(re.search(r"@import\(\"([^\"]*src|[^\"]*cwd|[^\"]*root)", text))
    return False

SAFE_CALLS = {"new","from","default","parse","open","load","read","write","format","vec","Some","Ok","Err","None","String",
              "Vec","Path","PathBuf","Duration","range","len","print","println","drop","assert","require","import","str",
              "int","float","list","dict","set","tuple","bool","isinstance","getattr","setattr","hasattr","super","self",
              "test","it","describe","beforeEach","afterEach","before","after","expect","jest","vi","mock","fn","spyOn",
              "pytest","fixture","parametrize","raises","mark","skip","xfail","assert_equal","assert_raises","deftest",
              "for","if","while","match","loop","return","catch","with","switch","else","case","try","except","finally",
              "in","is","not","and","or","del","lambda","yield","await","raise","pass","global","nonlocal","assert_eq",
              "let","create_dir","create_dir_all","remove_dir_all","remove_file","read_dir","metadata","canonicalize",
              "temp_dir","current_dir","set_var","var","sleep","now","elapsed","from_secs","from_millis","exists",
              "is_file","is_dir","to_path_buf","display","with_extension","set_extension","parent","file_name","components",
              "read_to_string","copy","rename","join_paths","env_var","args_os","exit","stdin","stdout","stderr",
              "from_str","to_bytestring","try_from","try_into","id","from_utf8","to_str","as_bytes","write_all"}
CALL_RE = re.compile(r"([A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)\s*\(")
FUNC_RE = re.compile(r"\b(?:pub\s+)?(?:async\s+)?(?:fn|def|func|function)\s+([A-Za-z_]\w*)|(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_]\w*\s*=>)")

STD_TYPES = {"String","Vec","Path","PathBuf","Duration","Instant","SystemTime","HashMap","BTreeMap","HashSet","BTreeSet",
             "OsStr","OsString","SocketAddr","IpAddr","Box","Arc","Rc","Cell","RefCell","Mutex","RwLock","Uuid","Regex",
             "Json","Value","Map","Seq","Number","Cow","Bytes","Chars","Iter","Option","Result","Range","VecDeque"}
STR_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

def calls_in(text):
    masked = STR_RE.sub('""', text)
    out = []
    for m in CALL_RE.finditer(masked):
        before = masked[m.start()-1] if m.start() else ""
        if before in {"!", "[", "#", "@"}: continue
        parts = [p.strip() for p in m.group(1).split("::")]
        out.append((parts[-1], before == ".", len(parts) > 1 and parts[0][:1].isupper(), parts[0]))
    return out

def function_map(repo):
    fmap = {}
    exts = {"rs","py","zig","go","js","ts","tsx","jsx","mjs","cjs","cs","lisp","el","rb","lua"}
    for rel in tracked(repo):
        if ext_of(rel) not in exts or any(x in SKIP_DIRS for x in rel.split("/")): continue
        try: text = open(os.path.join(repo, rel), encoding="utf-8", errors="ignore").read()
        except OSError: continue
        marks = [(m.start(), m.group(1) or m.group(2)) for m in FUNC_RE.finditer(text)]
        for i, (start, name) in enumerate(marks):
            stop = marks[i+1][0] if i + 1 < len(marks) else len(text)
            fmap.setdefault(name, []).append((rel, bool(spawn_hit(rel, text[start:stop]))))
    return fmap

def module_of(rel):
    parts = rel.split("/")
    stem = parts[-1].rsplit(".",1)[0]
    if stem in {"mod","index","__init__","main","lib"} and len(parts) > 1: return parts[-2]
    return stem

def imported_modules(rel, text):
    mods = set()
    for m in re.finditer(r"(?m)^\s*from\s+([\w.]+)\s+import|^\s*import\s+([\w.]+)", text):
        mod = m.group(1) or m.group(2)
        mods.add(mod.split(".")[0]); mods.add(mod.split(".")[-1])
    e = ext_of(rel)
    if e == "rs":
        for m in re.finditer(r"\buse\s+([A-Za-z_]\w*(?:::\w+)*)", text):
            path = m.group(1)
            if path.split("::")[0] not in {"std","core","alloc"}:
                mods.update({path.split("::")[0], path.split("::")[-1]})
    if e in {"js","ts","tsx","jsx","mjs","cjs"}:
        for m in re.finditer(r"""(?:from|require\()\s*["']([^"']+)["']""", text):
            mods.add(os.path.basename(m.group(1)).rsplit(".",1)[0])
    if e == "go":
        for m in re.finditer(r'"([\w./-]+)"', text):
            mods.add(m.group(1).rsplit("/",1)[-1])
    return {m for m in mods if m}

def spawns(name, rel, text, fmap, mods):
    defs = fmap.get(name)
    if not defs: return None
    same = [s for r, s in defs if r == rel]
    if same: return any(same)
    near = [s for r, s in defs if module_of(r) in mods]
    if near: return any(near)
    return any(s for _, s in defs)

def unit_proven(rel, text, fmap):
    if spawn_hit(rel, text): return False
    mods = imported_modules(rel, text)
    for name, method, type_path, head in calls_in(text):
        if type_path and head in STD_TYPES: continue
        hit = spawns(name, rel, text, fmap, mods)
        if hit is True: return False
        if hit is False: continue
        if type_path: continue
        if name in SAFE_CALLS or name[:1].isupper(): continue
        if method: continue
        return False
    return True

def classify_test(rel, text, names, fmap):
    named = e2e_named(rel)
    if named: return "e2e", named
    hit = spawn_hit(rel, text)
    if hit: return "e2e", hit
    if not internal_ref(rel, text, names): return "unknown", ""
    if not unit_proven(rel, text, fmap): return "unknown", ""
    return "unit", ""

def test_root(rel):
    parts = rel.split("/")
    for k, seg in enumerate(parts[:-1]):
        if seg.lower() in TEST_DIR_NAMES or TEST_PROJ_RE.search(seg):
            return "/".join(parts[:k+1])
    return ""

def drop_spans(src, spans):
    lines = src.split("\n")
    drop = set()
    for a, b in spans: drop.update(range(max(a, 0), b + 1))
    out, after = [], False
    for i, l in enumerate(lines):
        if i in drop:
            after = True; continue
        if after and l.strip() == "" and out and out[-1].strip() == "":
            after = False; continue
        if l.strip(): after = False
        out.append(l)
    while out and out[-1].strip() == "": out.pop()
    body = "\n".join(out)
    return body + "\n" if body else body

def rust_str_end(text, i):
    j = i - 1; hashes = 0
    while j >= 0 and text[j] == "#": hashes += 1; j -= 1
    if j >= 0 and text[j] == "r":
        close = '"' + "#" * hashes
        k = text.find(close, i + 1)
        return len(text) if k < 0 else k + len(close)
    k = i + 1
    while k < len(text):
        if text[k] == "\\": k += 2; continue
        if text[k] == '"': return k + 1
        k += 1
    return len(text)

def rust_brace_end(text, i):
    n = len(text); depth = 0; j = i
    while j < n:
        c = text[j]
        if c == '"': j = rust_str_end(text, j); continue
        if c == "'" and j + 2 < n and text[j + 2] == "'": j += 3; continue
        if text.startswith("//", j):
            k = text.find("\n", j); j = n if k < 0 else k; continue
        if text.startswith("/*", j):
            k = text.find("*/", j + 2); j = n if k < 0 else k + 2; continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return j + 1
        j += 1
    return n

def rust_item_end(text, i):
    n = len(text); j = i
    while j < n:
        c = text[j]
        if c == '"': j = rust_str_end(text, j); continue
        if c == "'" and j + 2 < n and text[j + 2] == "'": j += 3; continue
        if text.startswith("//", j):
            k = text.find("\n", j); j = n if k < 0 else k; continue
        if text.startswith("/*", j):
            k = text.find("*/", j + 2); j = n if k < 0 else k + 2; continue
        if c == "{": return rust_brace_end(text, j)
        if c == ";": return j + 1
        j += 1
    return n

RUST_ATTR_RE = re.compile(r"^\s*#\[.*\]\s*$")
RUST_CFG_TEST_RE = re.compile(r"^\s*#\[\s*cfg\(\s*(?:all\s*\(\s*)?test\b[^\]]*\]\s*$")
RUST_TEST_ATTR_RE = re.compile(r"^\s*#\[\s*(?:[A-Za-z_][\w:]*::)?test\s*(?:\(.*\))?\s*\]\s*$")

def rust_test_spans(text):
    lines = text.split("\n")
    starts, off = [], 0
    for l in lines: starts.append(off); off += len(l) + 1
    spans, i = [], 0
    while i < len(lines):
        if not (RUST_CFG_TEST_RE.match(lines[i]) or RUST_TEST_ATTR_RE.match(lines[i])):
            i += 1; continue
        a = i
        while a > 0 and RUST_ATTR_RE.match(lines[a-1]): a -= 1
        k = i + 1
        while k < len(lines) and RUST_ATTR_RE.match(lines[k]): k += 1
        while k < len(lines) and lines[k].strip() == "": k += 1
        if k >= len(lines): break
        end = rust_item_end(text, starts[k])
        last = text.count("\n", 0, end)
        spans.append({"start": a, "end": last, "text": "\n".join(lines[a:last+1])})
        i = last + 1
    return spans

def py_test_spans(text):
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError): return []
    lines = text.split("\n")
    spans = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not re.match(r"^test_?", n.name): continue
        elif isinstance(n, ast.ClassDef):
            if not re.match(r"^(?:Test[A-Z0-9_]|TestCase)", n.name): continue
        else:
            continue
        first = min([d.lineno for d in getattr(n, "decorator_list", [])] + [n.lineno])
        last = (getattr(n, "end_lineno", None) or n.lineno) - 1
        spans.append({"start": first - 1, "end": last, "text": "\n".join(lines[first-1:last+1])})
    return spans

ZIG_TEST_RE = re.compile(r"^[ \t]*test\b[^{;]*\{")

def zig_test_spans(text):
    lines = text.split("\n")
    starts, off = [], 0
    for l in lines: starts.append(off); off += len(l) + 1
    spans = []
    for i, l in enumerate(lines):
        m = ZIG_TEST_RE.match(l)
        if not m: continue
        brace = starts[i] + m.end() - 1
        end = rust_brace_end(text, brace)
        last = text.count("\n", 0, end)
        spans.append({"start": i, "end": last, "text": "\n".join(lines[i:last+1])})
    return spans

def test_spans(rel, text):
    e = ext_of(rel)
    if e == "rs": return rust_test_spans(text)
    if e == "py": return py_test_spans(text)
    if e == "zig": return zig_test_spans(text)
    return []

def strip_test_blocks(rel, src, fmap):
    drop = [(s["start"], s["end"]) for s in test_spans(rel, src) if unit_proven(rel, s["text"], fmap)]
    return drop_spans(src, drop) if drop else src

def cargo_trim(text, doomed=()):
    lines = text.split("\n")
    out, i, changed = [], 0, False
    while i < len(lines):
        h = re.match(r"^\s*\[\[?([^\]]+)\]\]?\s*(?:#.*)?$", lines[i])
        name = h.group(1).strip() if h else ""
        end = i
        if h:
            end = i + 1
            while end < len(lines) and not re.match(r"^\s*\[", lines[end]): end += 1
        drop = False
        if name == "test":
            block = "\n".join(lines[i:end])
            pm = re.search(r"^\s*path\s*=\s*\"([^\"]+)\"", block, re.M)
            nm = re.search(r"^\s*name\s*=\s*\"([^\"]+)\"", block, re.M)
            target = os.path.normpath(pm.group(1)).replace(os.sep, "/") if pm else ""
            drop = bool(target and target in doomed) or bool(nm and not target and nm.group(1) in {r.rsplit("/",1)[-1].rsplit(".",1)[0] for r in doomed})
        if drop:
            changed = True; i = end
            continue
        out.append(lines[i]); i += 1
    while out and out[-1].strip() == "": out.pop()
    return "\n".join(out) + "\n", changed

def plan_tests(repo, exclude, only=None, fmap=None):
    files = [f for f in tracked(repo) if not any(x in SKIP_DIRS for x in f.split("/")) and os.path.isfile(os.path.join(repo, f))]
    if only:
        scoped = {os.path.relpath(os.path.abspath(x), repo).replace(os.sep, "/") for x in only}
        files = [f for f in files if f in scoped]
    if not files: return [], [], {}
    names = project_names(repo)
    fmap = function_map(repo) if fmap is None else fmap
    cands, keeps = [], []
    for rel in files:
        if ignored(exclude, rel) or not test_candidate(rel): continue
        full = os.path.join(repo, rel)
        if ext_of(rel) in DATA_EXTS:
            cands.append(rel); continue
        try: text = open(full, encoding="utf-8", errors="ignore").read()
        except OSError:
            keeps.append((full, "keep-e2e:unreadable test file", 0)); continue
        verdict, why = classify_test(rel, text, names, fmap)
        if verdict == "e2e": keeps.append((full, "keep-e2e:" + why, 0))
        elif verdict == "unknown": keeps.append((full, "keep-unknown:no evidence it is a unit test", 0))
        else: cands.append(rel)
    roots = {test_root(p) for p, kind, _ in keeps if kind.startswith("keep-e2e")}
    roots.discard("")
    pending = []
    for rel in cands:
        if test_root(rel) in roots and any(s.lower() in FIXTURE_DIR_NAMES for s in rel.split("/")[:-1]):
            keeps.append((os.path.join(repo, rel), "keep-e2e:fixtures of end-to-end tests", 0)); continue
        pending.append(rel)
    cands = pending
    cargo = {}
    for rel in files:
        if rel.rsplit("/",1)[-1] == "Cargo.toml":
            try: cargo[rel] = open(os.path.join(repo, rel), encoding="utf-8", errors="ignore").read()
            except OSError: pass
    declared = set()
    for rel, text in cargo.items():
        sec = ""
        for line in text.split("\n"):
            h = re.match(r"^\s*\[\[?([^\]]+)\]\]?\s*$", line)
            if h: sec = h.group(1).strip(); continue
            m = re.match(r"^\s*path\s*=\s*\"([^\"]+)\"", line)
            if m and sec != "test" and not sec.startswith("dev-dependencies"):
                declared.add(os.path.normpath(os.path.join(rel.rsplit("/",1)[0], m.group(1))).replace(os.sep, "/"))
    remaining = [f for f in files if f not in set(cands) and f.rsplit("/",1)[-1] != "Cargo.toml"]
    blob = corpus(repo, remaining)
    deletes = []
    for rel in cands:
        base = rel.rsplit("/",1)[-1]
        stem = stem_of(rel)
        needles = [base] + ([stem] if len(stem) >= 8 and base not in COMMON_BASENAMES else [])
        if rel in declared:
            keeps.append((os.path.join(repo, rel), "keep-ref:declared as a Cargo target", 0)); continue
        if rel.encode() in blob or any(n not in COMMON_BASENAMES and n.encode() in blob for n in needles):
            keeps.append((os.path.join(repo, rel), "keep-ref:referenced by retained files", 0)); continue
        deletes.append(rel)
    edits = {}
    for rel, text in cargo.items():
        new, changed = cargo_trim(text, doomed=set(deletes))
        if changed and new != text: edits[os.path.join(repo, rel)] = new
    return deletes, keeps, edits

def apply(repo, dry=False, fmt=False, force=False, only=None, strip_tests=False):
    changes = []
    if not force:
        reason = policy_reason(repo)
        if reason.startswith("explicit off"):
            return [("", "skip-explicit-off", 0)]
        if not reason:
            return [("", "skip-not-enrolled", 0)]
    exclude = ignore_patterns(repo)
    tests = tests_on(repo, strip_tests)
    fmap = function_map(repo) if tests else {}
    deletes, keeps, edits = plan_tests(repo, exclude, only, fmap) if tests else ([], [], {})
    doomed = {os.path.join(repo, rel) for rel in deletes}
    hold = {p for p, kind, _ in keeps if kind.startswith(("keep-e2e", "keep-unknown", "keep-ref:"))}
    lf = lang_files(repo)
    if only:
        scoped = set(os.path.abspath(x) for x in only)
        lf = {k: [f for f in v if f in scoped] for k, v in lf.items()}
        lf = {k: v for k, v in lf.items() if v}
        if not lf:
            nodes_by_file, errs_before, containers = {}, collections.Counter(), {}
        else:
            nodes_by_file, errs_before, containers = scan_all(lf)
    else:
        nodes_by_file, errs_before, containers = scan_all(lf)
    for lang, files in lf.items():
        byfile = {f: nodes_by_file[f] for f in files if nodes_by_file.get(f)}
        targets = [f for f in files if byfile.get(f) or tests]
        if not targets: continue
        edited, orig = {}, {}
        for f in targets:
            if f in doomed or not os.path.isfile(f): continue
            try:
                src = open(f, encoding="utf-8", newline="").read()
            except UnicodeDecodeError:
                changes.append((f, "skip-encoding", 0)); continue
            ns = byfile.get(f, [])
            new = strip_src(src, ns, containers.get(f, ()))
            if tests and f not in hold:
                new = strip_test_blocks(f, new, fmap)
            if new != src:
                edited[f] = new; orig[f] = src
        if not edited: continue
        if dry:
            for f in edited: changes.append((f, "strip", len(byfile.get(f, []))))
            continue
        for f, new in edited.items():
            try:
                mode = os.stat(f).st_mode
                if not os.access(f, os.W_OK): os.chmod(f, mode | 0o200)
                open(f,"w",encoding="utf-8",newline="").write(new)
                os.chmod(f, mode)
            except OSError:
                changes.append((f, "REJECT_IO", 0))
        bad_io = {f for f, k, _ in changes if k == "REJECT_IO"}
        edited = {f: v for f, v in edited.items() if os.path.exists(f) and f not in bad_io}
        _, errs_after, _ = scan_all({lang: list(edited)})
        for f in list(edited):
            if errs_before.get(f, 0) == 0 and errs_after.get(f, 0) > 0:
                open(f,"w",encoding="utf-8",newline="").write(orig[f])
                changes.append((f, "REJECT_SYNTAX", len(byfile.get(f, []))))
                del edited[f]
        for f in edited:
            changes.append((f, "strip", len(byfile.get(f, []))))
            if fmt:
                c = fmt_cmd(repo, lang, f)
                if c: sh(c)
    for m in tracked(repo):
        if only and os.path.join(repo, m) not in {os.path.abspath(x) for x in only}: continue
        if not m.lower().endswith((".md",".mdx")): continue
        if any(x in SKIP_DIRS for x in m.split("/")): continue
        pol = md_policy(m)
        if pol == "legal":
            changes.append((os.path.join(repo,m), "keep-legal", 0)); continue
        if pol != "drop": continue
        if ignored(exclude, m): continue
        refs = refs_to(repo, m)
        if refs and not force:
            changes.append((os.path.join(repo,m), "keep-referenced", len(refs))); continue
        full = os.path.join(repo, m)
        if not os.path.exists(full):
            changes.append((full, "md-gone", 0)); continue
        changes.append((full, "rm-md", 0))
        if not dry: os.remove(full)
    if tests:
        for path, why, _ in keeps: changes.append((path, why, 0))
        for rel in deletes:
            full = os.path.join(repo, rel)
            if not os.path.exists(full):
                changes.append((full, "rm-test-gone", 0)); continue
            changes.append((full, "rm-test", 0))
            if not dry: os.remove(full)
        for full, text in edits.items():
            changes.append((full, "test-wiring", 0))
            if not dry:
                try:
                    mode = os.stat(full).st_mode
                    if not os.access(full, os.W_OK): os.chmod(full, mode | 0o200)
                    open(full,"w",encoding="utf-8",newline="").write(text)
                    os.chmod(full, mode)
                except OSError:
                    changes.append((full, "REJECT_IO", 0))
    return changes

def dirty(repo):
    return bool(git(repo,"status","--porcelain","--untracked-files=no").stdout.strip())

def default_scope(root):
    out = []
    for r in discover(root):
        if not r["owned"] or r["owner"] == "Inscendai": continue
        rel = os.path.relpath(r["path"], os.path.expanduser("~/dev"))
        if rel.startswith(("contributing/","sandbox/")): continue
        if any(x in rel for x in (".spike-work","inscend-followup","grok-presets-scratch")): continue
        out.append(r)
    return out

def staged(repo):
    return [f for f in git(repo,"diff","--cached","--name-only","--diff-filter=ACMR","-z").stdout.split("\0") if f]

def added_lines(repo, path):
    out = git(repo,"diff","--cached","-U0","-M","--",path).stdout
    lines = set()
    for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", out, re.M):
        start = int(m.group(1)); count = int(m.group(2) or 1)
        lines.update(range(start, start + count))
    return lines

def ignored(patterns, path):
    return any(fnmatch.fnmatch(path, pat) or path.startswith(pat.rstrip("/") + "/") for pat in patterns)

SWEEP_KEY = "cleanker.policy"

def setting(repo, key):
    v = git(repo,"config","--local","--get",key)
    if v.returncode == 0: return v.stdout.strip()
    v = git(repo,"config","--get",key)
    return v.stdout.strip() if v.returncode == 0 else ""

def remote_owner(repo):
    rem = git(repo,"remote","get-url","origin").stdout.strip()
    m = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?$", rem)
    return m.group(1) if m else ""

def shadowed(repo):
    local = git(repo,"config","--local","--get","core.hooksPath").stdout.strip()
    return local if local else ""

def policy_reason(repo):
    local = git(repo,"config","--local","--get",SWEEP_KEY)
    if local.returncode == 0:
        on = local.stdout.strip().lower() in {"true","1","yes","on"}
        return "explicit on" if on else "explicit off"
    owners = setting(repo,"cleanker.owners").replace(",", " ").split()
    if owners:
        owner = remote_owner(repo)
        if owner and owner in owners: return "owner " + owner
        if not owner:
            roots = setting(repo,"cleanker.roots").replace(",", " ").split()
            top = git(repo,"rev-parse","--show-toplevel").stdout.strip()
            for root in roots:
                root = os.path.expanduser(root)
                if top == root or top.startswith(root.rstrip("/") + "/"): return "path " + root
    merged = git(repo,"config","--get",SWEEP_KEY)
    if merged.returncode == 0 and merged.stdout.strip().lower() in {"true","1","yes","on"}:
        return "explicit on"
    return ""

def enrolled(repo):
    reason = policy_reason(repo)
    return bool(reason) and not reason.startswith("explicit off")

def enroll(paths, on):
    done = []
    for p in paths:
        if on: git(p,"config","--local",SWEEP_KEY,"true")
        else: git(p,"config","--local","--unset",SWEEP_KEY)
        done.append((p, enrolled(p)))
    return done

def ignore_patterns(top):
    raw = git(top,"show",":.cleankerignore").stdout
    if not raw:
        path = os.path.join(top, ".cleankerignore")
        raw = open(path).read() if os.path.exists(path) else ""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line in {"*", "**", "/*"}: continue
        out.append(line)
    return out

def pre_push() -> int:
    top = git(os.getcwd(),"rev-parse","--show-toplevel").stdout.strip()
    if not top or not enrolled(top): return 0
    if os.environ.get("CLEANKER_SKIP") == "1": return 0
    empty = git(top,"hash-object","-t","tree","/dev/null").stdout.strip()
    changed = set()
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) < 4: continue
        local_sha, remote_sha = parts[1], parts[3]
        if set(local_sha) == {"0"}: continue
        if set(remote_sha) != {"0"}:
            out = git(top,"diff","--name-only","-z","%s..%s" % (remote_sha, local_sha)).stdout
        elif git(top,"for-each-ref","--count=1","refs/remotes").stdout.strip():
            out = git(top,"log","--format=","--name-only","-z",local_sha,"--not","--remotes").stdout
        else:
            out = git(top,"diff","--name-only","-z","%s..%s" % (empty, local_sha)).stdout
        for f in out.split("\0"):
            f = f.strip("\n")
            if f: changed.add(f)
    if not changed: return 0
    patterns = ignore_patterns(top)
    files = [f for f in changed if not ignored(patterns, f) and not any(x in SKIP_DIRS for x in f.split("/"))]
    lf = collections.defaultdict(list)
    md = []
    for f in files:
        low = f.lower()
        if low.endswith((".md",".mdx")):
            if md_policy(f) == "drop": md.append(f)
            continue
        ext = low.rsplit(".",1)[-1] if "." in os.path.basename(low) else ""
        lang = LANG_OF_EXT.get(ext)
        full = os.path.join(top, f)
        if lang and os.path.isfile(full): lf[lang].append(full)
    nodes_by_file, _, _ = scan_all(lf)
    bad = []
    for f, nodes in nodes_by_file.items():
        for n in nodes:
            if classified(n["text"]) == "keep": continue
            bad.append((os.path.relpath(f, top), n["text"].strip().splitlines()[0][:60]))
    for m in md:
        if refs_in(top, m): continue
        bad.append((m, "unreferenced prose"))
    if tests_on(top):
        names = project_names(top)
        fmap = function_map(top)
        for f in files:
            full = os.path.join(top, f)
            try: text = open(full, encoding="utf-8", errors="ignore").read()
            except OSError: continue
            if test_candidate(f):
                if classify_test(f, text, names, fmap)[0] == "unit":
                    bad.append((f, "unit test (cleanker.strip-tests)"))
                continue
            if ext_of(f) not in {"rs","py","zig"} or e2e_named(f): continue
            if any(unit_proven(f, s["text"], fmap) for s in test_spans(f, text)):
                bad.append((f, "in-file unit test (cleanker.strip-tests)"))
    if not bad: return 0
    for path, why in bad[:40]:
        print("cleanker: %s: %s" % (path, why))
    print("cleanker: %d violation(s) in the commits being pushed; `cleanker clean` fixes them, CLEANKER_SKIP=1 or --no-verify bypasses" % len(bad))
    return 1

def hook() -> int:
    top = git(os.getcwd(),"rev-parse","--show-toplevel").stdout.strip()
    if not top: return 0
    if not enrolled(top): return 0
    gd = git(top,"rev-parse","--absolute-git-dir").stdout.strip()
    for marker in ("rebase-merge","rebase-apply","MERGE_HEAD","CHERRY_PICK_HEAD"):
        if os.path.exists(os.path.join(gd, marker)): return 0
    if os.environ.get("CLEANKER_SKIP") == "1": return 0
    if not os.environ.get("CLEANKER_IN_HOOK"):
        env = dict(os.environ, CLEANKER_IN_HOOK="1")
        for cand in (os.path.join(top, ".husky", "pre-commit"), os.path.join(gd, "hooks", "pre-commit")):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                if subprocess.run([cand], cwd=top, env=env).returncode: return 1
    patterns = ignore_patterns(top)
    bad = []
    hay = None
    blobs, tmp_of = {}, {}
    for f in staged(top):
        if ignored(patterns, f) or any(x in SKIP_DIRS for x in f.split("/")): continue
        low = f.lower()
        if low.endswith((".md",".mdx")):
            if md_policy(f) == "drop":
                if hay is None: hay = corpus(top, tracked(top))
                if refs_in(top, f, blob=hay): continue
            if md_policy(f) == "drop":
                bad.append((f, 0, "markdown: unreferenced prose; only README, AGENTS and machine-read docs survive"))
            continue
        ext = low.rsplit(".",1)[-1] if "." in os.path.basename(low) else ""
        lang = LANG_OF_EXT.get(ext)
        if not lang: continue
        data = subprocess.run(["git","-C",top,"show",":"+f],capture_output=True).stdout
        fd, tmp = tempfile.mkstemp(suffix="." + ext)
        os.close(fd)
        with open(tmp,"wb") as fh: fh.write(data)
        blobs[f] = (lang, data, tmp)
        tmp_of[tmp] = f
    by_lang = collections.defaultdict(list)
    for f, (lang, data, tmp) in blobs.items(): by_lang[lang].append(tmp)
    nodes_by_file, _, _ = scan_all(by_lang)
    for tmp, found in nodes_by_file.items():
        f = tmp_of.get(tmp)
        if not f: continue
        for n in found:
            if classified(n["text"]) == "keep": continue
            line = blobs[f][1].count(b"\n", 0, n["range"]["byteOffset"]["start"]) + 1
            if line in added_lines(top, f):
                bad.append((f, line, n["text"].strip().splitlines()[0][:70]))
    if tests_on(top):
        names = project_names(top)
        fmap = function_map(top)
        for f in staged(top):
            if ignored(patterns, f) or any(x in SKIP_DIRS for x in f.split("/")): continue
            if not test_candidate(f) or e2e_named(f): continue
            text = blobs[f][1].decode("utf-8", "ignore") if f in blobs else ""
            if not text:
                try: text = open(os.path.join(top, f), encoding="utf-8", errors="ignore").read()
                except OSError: continue
            if classify_test(f, text, names, fmap)[0] == "unit":
                bad.append((f, 0, "test: unit test (cleanker.strip-tests)"))
        for f, (lang, data, tmp) in blobs.items():
            if e2e_named(f) or test_candidate(f): continue
            text = data.decode("utf-8", "ignore")
            added = added_lines(top, f)
            hit = 0
            for s in test_spans(f, text):
                if not unit_proven(f, s["text"], fmap): continue
                if any(i + 1 in added for i in range(s["start"], s["end"] + 1)):
                    hit = s["start"] + 1; break
            if hit: bad.append((f, hit, "test: in-file unit test (cleanker.strip-tests)"))
    for _, _, tmp in blobs.values(): os.unlink(tmp)
    if not bad:
        return 0
    for f, line, why in bad:
        print("cleanker: %s%s: %s" % (f, ":%d" % line if line else "", why))
    print("cleanker: %d violation(s); `cleanker dry-run` previews the fix, `cleanker clean` writes it; CLEANKER_SKIP=1 or --no-verify bypasses" % len(bad))
    return 1

def paths_to_repos(args, root):
    out = []
    for raw in (args or [root]):
        if raw is None: continue
        p = os.path.abspath(os.path.expanduser(raw))
        probe = p if os.path.isdir(p) else os.path.dirname(p)
        top = git(probe,"rev-parse","--show-toplevel").stdout.strip()
        if top: out.append(top)
        elif os.path.isdir(p): out.extend(r["path"] for r in default_scope(p))
        else: print("cleanker: %s is not a repository or a directory" % raw, file=sys.stderr)
    seen = []
    for p in out:
        if p not in seen: seen.append(p)
    return seen

def main():
    ap = argparse.ArgumentParser(prog="cleanker", description="Remove comments and unreferenced prose.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("clean","dry-run"):
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="*", default=[])
        s.add_argument("--format", action="store_true", help="run the repository formatter afterwards")
        s.add_argument("--force", action="store_true", help="touch explicitly disabled repos and referenced docs")
        s.add_argument("--check", action="store_true", help="exit 1 when anything would change")
        s.add_argument("--file", action="append", default=[], help="restrict to these paths")
        s.add_argument("--strip-tests", action="store_true", help="remove non-end-to-end tests (also cleanker.strip-tests)")
    for name in ("status","enroll","disenroll"):
        s = sub.add_parser(name)
        s.add_argument("paths", nargs="*", default=[])
    sub.add_parser("hook", help="git pre-commit entry point")
    sub.add_parser("pre-push", help="git pre-push entry point")
    a = ap.parse_args()
    root = os.path.expanduser("~/dev")
    if a.cmd in {"hook","pre-push"}:
        try:
            sys.exit(hook() if a.cmd == "hook" else pre_push())
        except Exception as exc:
            print("cleanker: policy check skipped (%s: %s); commit allowed" % (exc.__class__.__name__, exc), file=sys.stderr)
            sys.exit(0)
    scope_default = root if a.cmd in {"status","enroll","disenroll"} else "."
    repos = paths_to_repos(a.paths or [scope_default], root)
    if a.cmd in {"enroll","disenroll"}:
        for p, state in enroll(repos, a.cmd == "enroll"):
            print("%-56s %-8s %s" % (os.path.relpath(p, os.path.expanduser("~")),
                                     "on" if state else "off", policy_reason(p) or "-"))
        return
    if a.cmd == "status":
        rows = []
        for r in discover(root):
            why = policy_reason(r["path"])
            local_hook = shadowed(r["path"])
            if why and local_hook: why = "shadowed by local hooksPath=" + local_hook
            rows.append((os.path.relpath(r["path"], os.path.expanduser("~")), why))
        on = [r for r in rows if r[1] and not r[1].startswith("explicit off") and not r[1].startswith("shadowed")]
        off = [r for r in rows if r not in on]
        print("enforced: %d   unenforced: %d" % (len(on), len(off)))
        for path, why in on: print("  on   %-48s %s" % (path, why))
        for path, why in off: print("  off  %-48s %s" % (path, why or "-"))
        return
    dry = a.cmd == "dry-run"
    total = collections.Counter()
    for path in repos:
        only = [os.path.abspath(x) for x in a.file] or None
        ch = apply(path, dry=dry, fmt=a.format, force=a.force, only=only,
                   strip_tests=getattr(a, "strip_tests", False))
        n = collections.Counter(k for _, k, _ in ch)
        if not ch: continue
        rm_tests = sum(v for k, v in n.items() if k in {"rm-test","rm-test-gone"} or k == "test-wiring")
        kept = sum(v for k, v in n.items() if k.startswith("keep-e2e") or k.startswith("keep-ref:"))
        print("%-52s strip=%-4d md=%-3d tests=%-3d kept=%-3d referenced=%-3d legal=%-2d reject=%d" % (
            os.path.relpath(path, os.path.expanduser("~")), n["strip"], n["rm-md"],
            rm_tests, kept, n["keep-referenced"], n["keep-legal"], n["REJECT_SYNTAX"]))
        for f, k, _ in ch:
            if k == "REJECT_SYNTAX": print("   rejected %s" % f)
            if k.startswith(("keep-e2e", "keep-ref:")):
                print("   kept %s (%s)" % (os.path.relpath(f, path), k.split(":",1)[-1]))
            if k in {"skip-not-enrolled", "skip-explicit-off"}:
                print("   skipped: %s (use --force to override)" % k.replace("skip-", ""), end="\n")
        for k in n: total[k] += n[k]
    if dry: print("(dry run; nothing written)")
    print("total", dict(total))
    if getattr(a, "check", False) and any(
            k in {"strip", "rm-md"} or k.startswith("rm-test") or k == "test-wiring" for k in total):
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stdout = None
        os._exit(0)
