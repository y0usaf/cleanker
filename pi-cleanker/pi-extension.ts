import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const run = (cwd: string, args: string[]) => {
  const r = spawnSync("cleanker", args, { cwd, encoding: "utf8" });
  return { code: r.status ?? 2, out: `${r.stdout ?? ""}${r.stderr ?? ""}` };
};

const counts = (out: string) => {
  const m = out.match(/strip=(\d+)\s+md=(\d+)/);
  return m ? Number(m[1]) + Number(m[2]) : 0;
};

const written = (input: unknown): string | undefined => {
  if (!input || typeof input !== "object") return undefined;
  const fields = ["path", "file_path", "file", "filename"] as const;
  for (const f of fields) {
    const v = (input as Record<string, unknown>)[f];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return undefined;
};

export default function (pi: ExtensionAPI) {
  pi.registerCommand("cleanker", {
    description: "Run cleanker: status, dry-run, or clean",
    handler: async (args, ctx) => {
      const sub = String(args ?? "").trim() || "status";
      const { code, out } = run(ctx.cwd, [sub]);
      const text = out.trim() || "no output";
      ctx.ui.notify(text.split("\n").slice(0, 12).join("\n"), code === 0 ? "info" : "warning");
    },
  });

  if (typeof pi.on !== "function") return;

  pi.on("tool_result", async (event, ctx) => {
    if (!event || event.isError) return;
    const rel = written(event.input);
    if (!rel) return;
    const abs = isAbsolute(rel) ? rel : join(ctx.cwd, rel);
    if (!existsSync(abs)) return;
    const fix = run(ctx.cwd, ["clean", "--file", abs]);
    const n = counts(fix.out);
    if (n > 0) ctx.ui.notify(`cleanker: ${n} change(s) in ${rel}`, "info");
  });

  pi.on("agent_end", async (_event, ctx) => {
    const check = run(ctx.cwd, ["dry-run", "--check"]);
    if (check.code === 0) return;
    if (check.code !== 1) {
      ctx.ui.notify(`cleanker: ${check.out.trim().split("\n").pop()}`, "warning");
      return;
    }
    const fix = run(ctx.cwd, ["clean"]);
    const n = counts(fix.out);
    if (n > 0) ctx.ui.notify(`cleanker: ${n} change(s) in ${ctx.cwd}`, "info");
  });
}
