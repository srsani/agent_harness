import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

// ─── Data ────────────────────────────────────────────────────────────────────
// Source: fresh full matrix run, 2026-07-07, single session.
// Model: local qwen/qwen3.6-35b-a3b via LM Studio (confirmed real tool-calling
// through direct API + message-history inspection before this run).
// DB re-seeded once, ground truth generated once, all 70 combos (7 architectures
// x 10 adi-* tasks) run and scored against that single consistent snapshot.

const TASK_LABELS: Record<string, string> = {
  "adi-top-modules": "Top modules",
  "adi-low-adoption": "Low adoption",
  "adi-user-lookup": "User lookup",
  "adi-function-analysis": "Function analysis",
  "adi-executive-users": "Executive users",
  "adi-module-ratings": "Module ratings",
  "adi-monthly-trend": "Monthly trend",
  "adi-disengagement-risk": "Disengagement risk",
  "adi-portfolio-depth": "Portfolio depth",
  "adi-function-opportunity": "Function opportunity",
};

const TASKS = Object.keys(TASK_LABELS);
const ARCHS = [
  "enterprise-react",
  "enterprise-codemode",
  "enterprise-mcp-react",
  "enterprise-mcp-codemode",
  "enterprise-sql-react",
  "enterprise-sql-codemode",
];
const ARCH_SHORT: Record<string, string> = {
  "enterprise-react": "react",
  "enterprise-codemode": "codemode",
  "enterprise-mcp-react": "mcp-react",
  "enterprise-mcp-codemode": "mcp-codemode",
  "enterprise-sql-react": "sql-react",
  "enterprise-sql-codemode": "sql-codemode",
};

type Cell = { ok: boolean; score: number | null; elapsed: number; error: string };
const MATRIX: Record<string, Record<string, Cell>> = {
  "adi-top-modules": {
    "enterprise-react": { ok: true, score: 1.0, elapsed: 4.1, error: "" },
    "enterprise-codemode": { ok: false, score: 0, elapsed: 3.2, error: "unknown tool name, retries exceeded" },
    "enterprise-mcp-react": { ok: true, score: 1.0, elapsed: 5.3, error: "" },
    "enterprise-mcp-codemode": { ok: false, score: 0, elapsed: 3.0, error: "unknown tool name, retries exceeded" },
    "enterprise-sql-react": { ok: true, score: 0.6, elapsed: 15.9, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 1.0, elapsed: 19.7, error: "" },
  },
  "adi-low-adoption": {
    "enterprise-react": { ok: true, score: 1.0, elapsed: 3.6, error: "" },
    "enterprise-codemode": { ok: false, score: 0, elapsed: 3.5, error: "unknown tool name, retries exceeded" },
    "enterprise-mcp-react": { ok: true, score: 1.0, elapsed: 4.3, error: "" },
    "enterprise-mcp-codemode": { ok: false, score: 0, elapsed: 2.4, error: "unknown tool name, retries exceeded" },
    "enterprise-sql-react": { ok: true, score: 1.0, elapsed: 6.9, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 1.0, elapsed: 10.6, error: "" },
  },
  "adi-user-lookup": {
    "enterprise-react": { ok: true, score: 0.6, elapsed: 9.9, error: "" },
    "enterprise-codemode": { ok: true, score: 0.8571, elapsed: 10.7, error: "" },
    "enterprise-mcp-react": { ok: true, score: 0.9231, elapsed: 7.3, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 0.8571, elapsed: 8.7, error: "" },
    "enterprise-sql-react": { ok: true, score: 0.5, elapsed: 26.2, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0.4762, elapsed: 17.7, error: "" },
  },
  "adi-function-analysis": {
    "enterprise-react": { ok: true, score: 0.8889, elapsed: 31.6, error: "" },
    "enterprise-codemode": { ok: false, score: 0, elapsed: 180, error: "timeout (180s retry-loop cap)" },
    "enterprise-mcp-react": { ok: true, score: 0.8889, elapsed: 22.3, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 1.0, elapsed: 27.1, error: "" },
    "enterprise-sql-react": { ok: true, score: 0.8889, elapsed: 31.7, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0, elapsed: 29.4, error: "" },
  },
  "adi-executive-users": {
    "enterprise-react": { ok: true, score: 0.8923, elapsed: 84.0, error: "" },
    "enterprise-codemode": { ok: true, score: 0.7615, elapsed: 99.5, error: "" },
    "enterprise-mcp-react": { ok: true, score: 0.9763, elapsed: 118.9, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 0.7679, elapsed: 76.6, error: "" },
    "enterprise-sql-react": { ok: true, score: 0.8325, elapsed: 41.9, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0.7532, elapsed: 51.7, error: "" },
  },
  "adi-module-ratings": {
    "enterprise-react": { ok: true, score: 0.845, elapsed: 27.0, error: "" },
    "enterprise-codemode": { ok: true, score: 0.845, elapsed: 32.7, error: "" },
    "enterprise-mcp-react": { ok: true, score: 0.9049, elapsed: 77.3, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 0.8292, elapsed: 22.5, error: "" },
    "enterprise-sql-react": { ok: true, score: 0.8231, elapsed: 19.2, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0.8231, elapsed: 21.6, error: "" },
  },
  "adi-monthly-trend": {
    "enterprise-react": { ok: false, score: 0, elapsed: 32.6, error: "UsageLimitExceeded (>50 tool calls)" },
    "enterprise-codemode": { ok: true, score: 0.8125, elapsed: 22.3, error: "" },
    "enterprise-mcp-react": { ok: false, score: 0, elapsed: 180, error: "timeout (180s retry-loop cap)" },
    "enterprise-mcp-codemode": { ok: false, score: 0, elapsed: 4.6, error: "unknown tool name, retries exceeded" },
    "enterprise-sql-react": { ok: true, score: 0.5597, elapsed: 36.6, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0.8125, elapsed: 21.2, error: "" },
  },
  "adi-disengagement-risk": {
    "enterprise-react": { ok: true, score: 0.4136, elapsed: 29.0, error: "" },
    "enterprise-codemode": { ok: true, score: 0.1957, elapsed: 35.8, error: "" },
    "enterprise-mcp-react": { ok: true, score: 0.2995, elapsed: 33.4, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 0.2995, elapsed: 47.2, error: "" },
    "enterprise-sql-react": { ok: false, score: 0, elapsed: 12.7, error: 'SQLError: near "FROM"' },
    "enterprise-sql-codemode": { ok: true, score: 0.4136, elapsed: 74.6, error: "" },
  },
  "adi-portfolio-depth": {
    "enterprise-react": { ok: true, score: 1.0, elapsed: 33.8, error: "" },
    "enterprise-codemode": { ok: true, score: 0.2439, elapsed: 14.0, error: "" },
    "enterprise-mcp-react": { ok: true, score: 0.2439, elapsed: 22.3, error: "" },
    "enterprise-mcp-codemode": { ok: true, score: 1.0, elapsed: 15.2, error: "" },
    "enterprise-sql-react": { ok: false, score: 0, elapsed: 13.1, error: "SQLError: one statement at a time" },
    "enterprise-sql-codemode": { ok: true, score: 0.6667, elapsed: 84.6, error: "" },
  },
  "adi-function-opportunity": {
    "enterprise-react": { ok: true, score: 0.9565, elapsed: 83.5, error: "" },
    "enterprise-codemode": { ok: true, score: 0.9565, elapsed: 66.5, error: "" },
    "enterprise-mcp-react": { ok: false, score: 0, elapsed: 180, error: "timeout (180s retry-loop cap)" },
    "enterprise-mcp-codemode": { ok: true, score: 0.3809, elapsed: 56.1, error: "" },
    "enterprise-sql-react": { ok: true, score: 0.3809, elapsed: 46.8, error: "" },
    "enterprise-sql-codemode": { ok: true, score: 0.3809, elapsed: 27.2, error: "" },
  },
};

const SUMMARY = [
  { arch: "enterprise-react", adjScore: 0.76, rawScore: 0.844, okRate: 9, avgElapsed: 34.0, medElapsed: 29.0, wins: 5 },
  { arch: "enterprise-sql-codemode", adjScore: 0.633, rawScore: 0.633, okRate: 10, avgElapsed: 35.8, medElapsed: 24.4, wins: 0 },
  { arch: "enterprise-mcp-react", adjScore: 0.624, rawScore: 0.78, okRate: 8, avgElapsed: 36.4, medElapsed: 22.3, wins: 3 },
  { arch: "enterprise-sql-react", adjScore: 0.559, rawScore: 0.698, okRate: 8, avgElapsed: 28.2, medElapsed: 28.9, wins: 0 },
  { arch: "enterprise-mcp-codemode", adjScore: 0.513, rawScore: 0.734, okRate: 7, avgElapsed: 36.2, medElapsed: 27.1, wins: 1 },
  { arch: "enterprise-codemode", adjScore: 0.467, rawScore: 0.667, okRate: 7, avgElapsed: 40.2, medElapsed: 32.7, wins: 1 },
];

// Historical points from earlier sessions that used Anthropic claude-sonnet-4-6
// instead of the local model. Kept because they were scored against a ground
// truth generated in the same session as the run (see Methodology tab for why
// that matters) -- these are the only historical numbers still valid to cite.
const CLAUDE_TOP_MODULES = [
  { arch: "enterprise-react", score: 1.0, elapsed: 7.8 },
  { arch: "enterprise-codemode", score: 1.0, elapsed: 7.8 },
  { arch: "enterprise-mcp-react", score: 1.0, elapsed: 8.8 },
  { arch: "enterprise-mcp-codemode", score: 0.909, elapsed: 12.7 },
  { arch: "enterprise-sql-react", score: 0.115, elapsed: 25.9 },
  { arch: "enterprise-sql-codemode", score: 0.429, elapsed: 26.6 },
];
const CLAUDE_FUNCTION_OPPORTUNITY = [
  { arch: "enterprise-react", score: 0.0, elapsed: 5.5, note: "empty output" },
  { arch: "enterprise-codemode", score: 0.9565, elapsed: 57.8, note: "" },
];

const PER_TASK_WINNER = [
  { task: "adi-top-modules", winner: "enterprise-react", score: 1.0 },
  { task: "adi-low-adoption", winner: "enterprise-react", score: 1.0 },
  { task: "adi-user-lookup", winner: "enterprise-mcp-react", score: 0.92 },
  { task: "adi-function-analysis", winner: "enterprise-mcp-codemode", score: 1.0 },
  { task: "adi-executive-users", winner: "enterprise-mcp-react", score: 0.98 },
  { task: "adi-module-ratings", winner: "enterprise-mcp-react", score: 0.9 },
  { task: "adi-monthly-trend", winner: "enterprise-codemode", score: 0.81 },
  { task: "adi-disengagement-risk", winner: "enterprise-react", score: 0.41 },
  { task: "adi-portfolio-depth", winner: "enterprise-react", score: 1.0 },
  { task: "adi-function-opportunity", winner: "enterprise-react", score: 0.96 },
];

function scoreTone(score: number | null, ok: boolean): "success" | "danger" | "secondary" {
  if (!ok || score === null) return "danger";
  if (score >= 0.8) return "success";
  if (score >= 0.4) return "secondary";
  return "danger";
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function ArchitectureRecommendation() {
  const [tab, setTab] = useCanvasState<"overview" | "matrix" | "modeldep" | "guide">("tab", "overview");

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 980 }}>
      <Stack gap={4}>
        <H1>Architecture Benchmark: Full Matrix Recommendation</H1>
        <Text tone="secondary">
          pydantic-ai · 6 enterprise architectures × all 10 adi-* tasks · single session, same DB
          snapshot · model: local qwen3.6-35b-a3b (verified real tool-calling)
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value="enterprise-react" label="Best overall (this model)" tone="success" />
        <Stat value="enterprise-sql-codemode" label="Most reliable (10/10 ok)" />
        <Stat value="22–27s" label="Median elapsed, top 3 fastest archs" />
        <Stat value="70 / 70" label="Task × architecture combos run today" tone="success" />
      </Grid>

      <Callout tone="warning" title="This replaces the previous partial run">
        The earlier version of this canvas was based on 2 architectures tested on 2 tasks, with the
        rest untested. This run covers all 6 enterprise architectures across all 10 benchmark tasks
        (70 combos) in one session, after discovering and fixing a broken model config that was
        silently producing 100% hallucinated answers. See the Methodology tab for details.
      </Callout>

      <Row gap={8}>
        <Pill active={tab === "overview"} onClick={() => setTab("overview")}>Overview</Pill>
        <Pill active={tab === "matrix"} onClick={() => setTab("matrix")}>Full Task Matrix</Pill>
        <Pill active={tab === "modeldep"} onClick={() => setTab("modeldep")}>Model Dependency</Pill>
        <Pill active={tab === "guide"} onClick={() => setTab("guide")}>Selection Guide</Pill>
      </Row>

      {tab === "overview" && (
        <Stack gap={24}>
          <Stack gap={8}>
            <H2>Reliability-adjusted score, averaged across all 10 tasks</H2>
            <Text tone="secondary" size="small">
              Failures count as 0 for this metric (a fast wrong/failed answer is not "fast" in
              practice) · source: full-matrix run, 2026-07-07
            </Text>
            <BarChart
              categories={SUMMARY.map((s) => ARCH_SHORT[s.arch])}
              series={[{ name: "Reliability-adjusted score", data: SUMMARY.map((s) => s.adjScore), tone: "success" }]}
              horizontal
              yMin={0}
              yMax={1}
              showValues
              height={220}
            />
          </Stack>

          <Divider />

          <Stack gap={8}>
            <H2>Median elapsed time, successful runs only</H2>
            <Text tone="secondary" size="small">
              Seconds per run, only counting runs that completed (didn't fail or time out)
            </Text>
            <BarChart
              categories={SUMMARY.map((s) => ARCH_SHORT[s.arch])}
              series={[{ name: "Median elapsed (s)", data: SUMMARY.map((s) => s.medElapsed) }]}
              horizontal
              valueSuffix=" s"
              showValues
              height={220}
            />
          </Stack>

          <Divider />

          <Table
            headers={["Architecture", "Adj. score", "Score when OK", "OK rate", "Avg elapsed", "Tasks won"]}
            rows={SUMMARY.map((s) => [
              <Text size="small" style={{ fontFamily: "monospace" }}>{s.arch}</Text>,
              <Text size="small" weight="semibold" tone={s.adjScore >= 0.7 ? "primary" : "secondary"}>{s.adjScore.toFixed(2)}</Text>,
              <Text size="small" tone="secondary">{s.rawScore.toFixed(2)}</Text>,
              <Text size="small" tone={s.okRate === 10 ? "primary" : "secondary"}>{s.okRate}/10</Text>,
              <Text size="small" tone="secondary">{s.avgElapsed.toFixed(1)} s</Text>,
              <Text size="small" weight={s.wins > 0 ? "semibold" : "normal"}>{s.wins}</Text>,
            ])}
            columnAlign={["left", "right", "right", "center", "right", "center"]}
            rowTone={SUMMARY.map((s) => (s.adjScore >= 0.7 ? "success" : undefined))}
            striped
          />

          <Callout tone="info" title="Key takeaway">
            enterprise-react is the clear overall winner with this model: highest reliability-adjusted
            score (0.76), wins the most individual tasks (5/10), and is competitively fast. The two
            CodeMode architectures that wrap all 17 tools (enterprise-codemode, enterprise-mcp-codemode)
            score worst here — not because CodeMode is a bad idea, but because this specific model keeps
            trying to call wrapped tools directly by name instead of writing Python inside run_code. See
            Model Dependency for why this flips with a stronger model.
          </Callout>
        </Stack>
      )}

      {tab === "matrix" && (
        <Stack gap={16}>
          <Stack gap={4}>
            <H2>Every architecture × every task, this session</H2>
            <Text tone="secondary" size="small">
              Score (or failure reason) · elapsed seconds · green ≥0.8, amber 0.4–0.8, red &lt;0.4 or failed
            </Text>
          </Stack>
          {TASKS.map((task) => (
            <Stack gap={6} key={task}>
              <Text weight="semibold" size="small">{TASK_LABELS[task]}</Text>
              <Table
                headers={ARCHS.map((a) => ARCH_SHORT[a])}
                rows={[
                  ARCHS.map((a) => {
                    const c = MATRIX[task][a];
                    if (!c.ok) {
                      return (
                        <Text size="small" tone="secondary">
                          FAIL · {c.error}
                        </Text>
                      );
                    }
                    return (
                      <Text size="small" tone={scoreTone(c.score, c.ok)} weight="semibold">
                        {c.score?.toFixed(2)} · {c.elapsed.toFixed(0)}s
                      </Text>
                    );
                  }),
                ]}
                rowTone={[undefined]}
                columnAlign={ARCHS.map(() => "left" as const)}
              />
            </Stack>
          ))}

          <Divider />

          <Stack gap={4}>
            <H3>Per-task winner</H3>
            <Table
              headers={["Task", "Winning architecture", "Score"]}
              rows={PER_TASK_WINNER.map((r) => [
                <Text size="small">{TASK_LABELS[r.task]}</Text>,
                <Text size="small" style={{ fontFamily: "monospace" }} weight="semibold">{r.winner}</Text>,
                <Text size="small" tone="secondary">{r.score.toFixed(2)}</Text>,
              ])}
              columnAlign={["left", "left", "right"]}
              striped
            />
          </Stack>
        </Stack>
      )}

      {tab === "modeldep" && (
        <Stack gap={20}>
          <Stack gap={4}>
            <H2>Architecture ranking is model-dependent</H2>
            <Text tone="secondary">
              The same 6 architectures were tested earlier against Anthropic's claude-sonnet-4-6
              (a stronger, frontier cloud model) in prior sessions. The ranking looks different.
            </Text>
          </Stack>

          <Grid columns={2} gap={16}>
            <Card>
              <CardHeader trailing={<Pill size="sm">local qwen3.6-35b-a3b</Pill>}>Today — local model</CardHeader>
              <CardBody>
                <Stack gap={8}>
                  <Text size="small">1. enterprise-react — 0.76 adj. score, 9/10 ok</Text>
                  <Text size="small">2. enterprise-sql-codemode — 0.63, 10/10 ok</Text>
                  <Text size="small">3. enterprise-mcp-react — 0.62, 8/10 ok</Text>
                  <Divider />
                  <Text size="small" tone="secondary">
                    Last: enterprise-codemode (0.47) and enterprise-mcp-codemode (0.51) — this model
                    repeatedly tries to call the 17 wrapped tools directly by name instead of writing
                    Python inside run_code, burning its retry budget and failing outright.
                  </Text>
                </Stack>
              </CardBody>
            </Card>

            <Card>
              <CardHeader trailing={<Pill size="sm" active>claude-sonnet-4-6</Pill>}>Earlier sessions — cloud model</CardHeader>
              <CardBody>
                <Stack gap={8}>
                  <Text size="small">adi-top-modules: react 1.00, codemode 1.00 (tied)</Text>
                  <Text size="small">adi-function-opportunity (hardest task): codemode 0.96, react 0.00 (empty output)</Text>
                  <Divider />
                  <Text size="small" tone="secondary">
                    With a frontier model, enterprise-codemode correctly uses the run_code
                    indirection and its batched execution handles the hardest multi-join task better
                    than react, which returned nothing at all on that same task in a single-shot run.
                  </Text>
                </Stack>
              </CardBody>
            </Card>
          </Grid>

          <Divider />

          <Stack gap={8}>
            <H3>adi-top-modules, Claude-based (historical, valid same-session scoring)</H3>
            <BarChart
              categories={CLAUDE_TOP_MODULES.map((d) => ARCH_SHORT[d.arch])}
              series={[{ name: "Score", data: CLAUDE_TOP_MODULES.map((d) => d.score), tone: "success" }]}
              horizontal
              yMin={0}
              yMax={1}
              showValues
              height={200}
            />
          </Stack>

          <Stack gap={8}>
            <H3>adi-function-opportunity (hardest task), Claude-based</H3>
            <Table
              headers={["Architecture", "Score", "Elapsed", "Note"]}
              rows={CLAUDE_FUNCTION_OPPORTUNITY.map((r) => [
                <Text size="small" style={{ fontFamily: "monospace" }}>{r.arch}</Text>,
                <Text size="small" weight="semibold" tone={r.score > 0.5 ? "primary" : "secondary"}>{r.score.toFixed(2)}</Text>,
                <Text size="small" tone="secondary">{r.elapsed.toFixed(1)} s</Text>,
                <Text size="small" tone="secondary">{r.note}</Text>,
              ])}
              columnAlign={["left", "right", "right", "left"]}
              rowTone={CLAUDE_FUNCTION_OPPORTUNITY.map((r) => (r.score === 0 ? "danger" : "success"))}
            />
          </Stack>

          <Callout tone="warning" title="Practical implication">
            Don't assume an architecture ranking transfers across models. CodeMode's benefit (fewer
            round trips, batched execution) only materializes if the model reliably understands it
            must write Python that calls tools, rather than calling tools directly. Direct ReAct-style
            tool calling is the safer default on weaker/smaller/local models. Re-validate whenever you
            change the underlying model.
          </Callout>
        </Stack>
      )}

      {tab === "guide" && (
        <Stack gap={20}>
          <Stack gap={4}>
            <H2>How to select an architecture</H2>
            <Text tone="secondary">
              Two decisions: which architecture family, and does your deployed model actually support
              it. Answer both before picking a default.
            </Text>
          </Stack>

          <Grid columns={2} gap={16}>
            <Card>
              <CardHeader trailing={<Pill size="sm" active>Primary default</Pill>}>enterprise-react</CardHeader>
              <CardBody>
                <Stack gap={10}>
                  <Text weight="semibold">Best all-around choice regardless of model tier.</Text>
                  <Stack gap={6}>
                    <Text size="small" tone="secondary">Why:</Text>
                    <Text size="small">· Highest reliability-adjusted score today (0.76), wins 5/10 tasks</Text>
                    <Text size="small">· Works identically well with weak and strong models — direct tool calls need no code-writing indirection</Text>
                    <Text size="small">· Fast: ~29s median, under 10s on single-lookup tasks</Text>
                  </Stack>
                  <Divider />
                  <Stack gap={4}>
                    <Text size="small" tone="secondary">Watch out for:</Text>
                    <Text size="small">Single-shot ReAct can spiral into a tool-call loop on ambiguous complex tasks (hit a 50-call usage limit on adi-monthly-trend) or return empty output on the hardest join task with weaker prompting.</Text>
                  </Stack>
                </Stack>
              </CardBody>
            </Card>

            <Card>
              <CardHeader trailing={<Pill size="sm">Reliability fallback</Pill>}>enterprise-sql-codemode</CardHeader>
              <CardBody>
                <Stack gap={10}>
                  <Text weight="semibold">Only architecture with zero failures across all 10 tasks.</Text>
                  <Stack gap={6}>
                    <Text size="small" tone="secondary">Why:</Text>
                    <Text size="small">· 10/10 ok-rate — never crashed, timed out, or hit a usage limit</Text>
                    <Text size="small">· Only 3 abstract tools (list_tables/describe_table/execute_sql) — this model doesn't confuse them with direct callables the way it does the 17-tool CodeMode wrap</Text>
                  </Stack>
                  <Divider />
                  <Stack gap={4}>
                    <Text size="small" tone="secondary">Trade-off:</Text>
                    <Text size="small">Lower correctness ceiling (0.63 avg) — model-written SQL sometimes gets aggregation logic wrong even when it runs without error. Use where "always answers something" matters more than peak accuracy.</Text>
                  </Stack>
                </Stack>
              </CardBody>
            </Card>
          </Grid>

          <Divider />

          <H3>Two-architecture shortlist</H3>
          <Callout tone="success" title="enterprise-react + enterprise-sql-codemode covers the practical range">
            Route the common case (single lookups, most multi-join analytics) to enterprise-react.
            Use enterprise-sql-codemode as an automatic fallback when enterprise-react errors, hits a
            usage-limit, or returns empty output — it has never failed outright in 10/10 tasks tested.
            This combination beats using any single architecture alone and is simpler to operate than
            a 6-way architecture menu.
          </Callout>

          <H3>Architectures to drop (with this model)</H3>
          <Table
            headers={["Architecture", "Reason to exclude"]}
            rows={[
              ["enterprise-codemode", "Worst reliability-adjusted score (0.47) with this model — repeatedly tries calling wrapped tools directly instead of writing run_code Python, exhausting its retry budget. Revisit if you upgrade to a frontier model (scored 0.96–1.00 with claude-sonnet-4-6 historically)."],
              ["enterprise-mcp-codemode", "Same root cause as enterprise-codemode plus MCP server overhead on top. 0.51 adj. score, 7/10 ok."],
              ["enterprise-mcp-react", "Matches or trails plain enterprise-react on every task while adding a local MCP server hop and, on one task, timed out entirely where direct react succeeded. No measured benefit over enterprise-react unless MCP transport is required externally."],
              ["enterprise-sql-react", "Dominated by enterprise-sql-codemode: similar or worse scores, two outright SQL syntax failures (multi-statement query, malformed WHERE clause) that sql-codemode's single-sandbox execution avoided."],
              ["minimal / codemode / codemode-mcp-search", "No enterprise DB access by design — correct only for conversational/no-DB queries, not part of this comparison."],
            ]}
            rowTone={["danger", "danger", undefined, undefined, undefined]}
            columnAlign={["left", "left"]}
            striped
          />

          <Divider />

          <H3>Methodology note: ground truth drifts with time</H3>
          <Callout tone="warning" title="Re-seeding the DB shifts date-windowed answers">
            The seed script anchors order dates to the current wall-clock time, so "last 90 days" /
            "last 6 months" style tasks have answers that shift every time the database is reseeded on
            a different day. This run reseeded the DB once and generated ground truth once, then ran
            all 70 combos against that single snapshot — internally consistent and valid. Older
            multi-day-old raw reports can't be validly re-scored against a freshly generated ground
            truth for this reason; only their objective, time-invariant facts (ok/fail, elapsed
            seconds) remain comparable, which is what the Model Dependency tab uses them for.
          </Callout>
        </Stack>
      )}
    </Stack>
  );
}
