import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, lstatSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const READ_TOOLS = new Set(["read", "grep", "find", "ls", "view_file"]);
const WRITE_FIELDS = ["path", "file_path", "file", "filename", "TargetFile"] as const;
const CWD_FIELDS = ["cwd", "Cwd"] as const;

type Snapshot = { root: string; files: Map<string, string> };

const run = (cwd: string, args: string[]) => {
  const r = spawnSync("cleanker", args, { cwd, encoding: "utf8" });
  return { code: r.status ?? 2, out: `${r.stdout ?? ""}${r.stderr ?? ""}` };
};

const counts = (out: string) => {
  const m = out.match(/strip=(\d+)\s+md=(\d+)(?:\s+tests=(\d+))?/);
  return m ? Number(m[1]) + Number(m[2]) + Number(m[3] ?? 0) : 0;
};

const written = (input: unknown): string | undefined => {
  if (!input || typeof input !== "object") return undefined;
  for (const f of WRITE_FIELDS) {
    const v = (input as Record<string, unknown>)[f];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return undefined;
};

const toolCwd = (input: unknown, fallback: string): string => {
  if (input && typeof input === "object") {
    for (const f of CWD_FIELDS) {
      const v = (input as Record<string, unknown>)[f];
      if (typeof v === "string" && v.length > 0 && existsSync(v)) return v;
    }
  }
  return fallback;
};

const repoRoot = (dir: string): string | null => {
  if (!existsSync(dir)) return null;
  const r = spawnSync("git", ["-C", dir, "rev-parse", "--show-toplevel"], { encoding: "utf8" });
  if (r.status !== 0) return null;
  const top = r.stdout.trim();
  return top || null;
};

const fingerprint = (abs: string): string | null => {
  try {
    const st = lstatSync(abs);
    if (st.isSymbolicLink() || !st.isFile()) return null;
    if (st.size <= 2_000_000) {
      const h = createHash("sha256").update(readFileSync(abs)).digest("hex");
      return `${st.size}:${h}`;
    }
    return `${st.size}:${st.mtimeMs}`;
  } catch {
    return null;
  }
};

const snapshot = (dir: string): Snapshot | null => {
  const root = repoRoot(dir);
  if (!root) return null;
  const st = spawnSync("git", ["-C", root, "status", "--porcelain=v1", "-z", "-uall"], {
    encoding: "utf8",
  });
  if (st.status !== 0) return null;
  const parts = st.stdout.split("\0");
  const files = new Map<string, string>();
  for (let i = 0; i < parts.length; i++) {
    const entry = parts[i];
    if (!entry) continue;
    const xy = entry.slice(0, 2);
    const rel = entry.slice(3);
    if (xy[0] === "R" || xy[0] === "C" || xy[1] === "R" || xy[1] === "C") {
      i++;
    }
    if (!rel) continue;
    const abs = resolve(root, rel);
    const fp = fingerprint(abs);
    if (fp !== null) files.set(abs, fp);
  }
  return { root, files };
};

const keyOf = (event: { toolCallId?: unknown }) =>
  typeof event.toolCallId === "string" && event.toolCallId.length > 0 ? event.toolCallId : "__default__";

export default function (pi: ExtensionAPI) {
  const touched = new Set<string>();
  const pending = new Map<string, { cwd: string; snap: Snapshot }>();

  pi.registerCommand("cleanker", {
    description: "Run cleanker: status, dry-run, or clean",
    handler: async (args, ctx) => {
      const parts = String(args ?? "").trim().split(/\s+/).filter(Boolean);
      const { code, out } = run(ctx.cwd, parts.length > 0 ? parts : ["status"]);
      const text = out.trim() || "no output";
      ctx.ui.notify(text.split("\n").slice(0, 12).join("\n"), code === 0 ? "info" : "warning");
    },
  });

  if (typeof pi.on !== "function") return;

  pi.on("tool_call", async (event, ctx) => {
    if (!event) return;
    if (typeof event.toolName === "string" && READ_TOOLS.has(event.toolName)) return;
    if (written(event.input)) return;
    const dir = toolCwd(event.input, ctx.cwd);
    const snap = snapshot(dir);
    if (snap) pending.set(keyOf(event), { cwd: dir, snap });
  });

  pi.on("tool_result", async (event, ctx) => {
    const k = event ? keyOf(event) : "__default__";
    const pre = pending.get(k);
    pending.delete(k);
    if (!event || event.isError) return;
    if (typeof event.toolName === "string" && READ_TOOLS.has(event.toolName)) return;
    const rel = written(event.input);
    if (rel) {
      const abs = isAbsolute(rel) ? rel : join(ctx.cwd, rel);
      if (!existsSync(abs)) return;
      touched.add(abs);
      const cwd = repoRoot(dirname(abs)) ?? ctx.cwd;
      const fix = run(cwd, ["clean", "--file", abs]);
      const n = counts(fix.out);
      if (n > 0) ctx.ui.notify(`cleanker: ${n} change(s) in ${rel}`, "info");
      return;
    }
    if (!pre) return;
    const post = snapshot(pre.cwd);
    if (!post) return;
    const changed: string[] = [];
    for (const [abs, fp] of post.files) {
      if (pre.snap.files.get(abs) !== fp && existsSync(abs)) {
        touched.add(abs);
        changed.push(abs);
      }
    }
    if (changed.length === 0) return;
    const fix = run(post.root, ["clean", ...changed.flatMap((f) => ["--file", f])]);
    const n = counts(fix.out);
    if (n > 0) ctx.ui.notify(`cleanker: ${n} change(s) in ${post.root}`, "info");
  });

  pi.on("agent_end", async (_event, ctx) => {
    const files = [...touched].filter((p) => existsSync(p));
    touched.clear();
    if (files.length === 0) return;
    const byRoot = new Map<string, string[]>();
    for (const f of files) {
      const dir = repoRoot(dirname(f)) ?? ctx.cwd;
      const list = byRoot.get(dir);
      if (list) list.push(f);
      else byRoot.set(dir, [f]);
    }
    for (const [dir, group] of byRoot) {
      const fileArgs = group.flatMap((f) => ["--file", f]);
      const check = run(dir, ["dry-run", "--check", ...fileArgs]);
      if (check.code === 0) continue;
      if (check.code !== 1) {
        ctx.ui.notify(`cleanker: ${check.out.trim().split("\n").pop()}`, "warning");
        continue;
      }
      const fix = run(dir, ["clean", ...fileArgs]);
      const n = counts(fix.out);
      if (n > 0) ctx.ui.notify(`cleanker: ${n} change(s) in ${dir}`, "info");
    }
  });
}
