import {
  bigserial,
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  real,
  text,
  timestamp,
} from "drizzle-orm/pg-core"

// --- Better Auth tables (Better Auth-managed; do not rename columns) ---

export const user = pgTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified")
    .$defaultFn(() => false)
    .notNull(),
  image: text("image"),
  // v2: user-level W&B API key for sandbox training (nullable).
  wandbApiKey: text("wandb_api_key"),
  createdAt: timestamp("created_at")
    .$defaultFn(() => new Date())
    .notNull(),
  updatedAt: timestamp("updated_at")
    .$defaultFn(() => new Date())
    .notNull(),
})

export const session = pgTable("session", {
  id: text("id").primaryKey(),
  expiresAt: timestamp("expires_at").notNull(),
  token: text("token").notNull().unique(),
  createdAt: timestamp("created_at").notNull(),
  updatedAt: timestamp("updated_at").notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  userId: text("user_id")
    .notNull()
    .references(() => user.id, { onDelete: "cascade" }),
})

export const account = pgTable("account", {
  id: text("id").primaryKey(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  userId: text("user_id")
    .notNull()
    .references(() => user.id, { onDelete: "cascade" }),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: timestamp("access_token_expires_at"),
  refreshTokenExpiresAt: timestamp("refresh_token_expires_at"),
  scope: text("scope"),
  password: text("password"),
  createdAt: timestamp("created_at").notNull(),
  updatedAt: timestamp("updated_at").notNull(),
})

export const verification = pgTable("verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at").notNull(),
  createdAt: timestamp("created_at").$defaultFn(() => new Date()),
  updatedAt: timestamp("updated_at").$defaultFn(() => new Date()),
})

export const apikey = pgTable(
  "apikey",
  {
    id: text("id").primaryKey(),
    configId: text("config_id")
      .$defaultFn(() => "default")
      .notNull(),
    name: text("name"),
    start: text("start"),
    referenceId: text("reference_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    prefix: text("prefix"),
    key: text("key").notNull(),
    refillInterval: integer("refill_interval"),
    refillAmount: integer("refill_amount"),
    lastRefillAt: timestamp("last_refill_at"),
    enabled: boolean("enabled").$defaultFn(() => true),
    rateLimitEnabled: boolean("rate_limit_enabled").$defaultFn(() => true),
    rateLimitTimeWindow: integer("rate_limit_time_window").$defaultFn(
      () => 86400000,
    ),
    rateLimitMax: integer("rate_limit_max").$defaultFn(() => 10),
    requestCount: integer("request_count").$defaultFn(() => 0),
    remaining: integer("remaining"),
    lastRequest: timestamp("last_request"),
    expiresAt: timestamp("expires_at"),
    createdAt: timestamp("created_at")
      .$defaultFn(() => new Date())
      .notNull(),
    updatedAt: timestamp("updated_at")
      .$defaultFn(() => new Date())
      .notNull(),
    permissions: text("permissions"),
    metadata: text("metadata"),
  },
  (table) => [
    index("apikey_config_id_idx").on(table.configId),
    index("apikey_reference_id_idx").on(table.referenceId),
    index("apikey_key_idx").on(table.key),
  ],
)

// --- App tables v2 (see infra/architecture-v2.md for the contract) ---
// DB-side defaults throughout (.default(...)/.defaultNow()) — keep them DB-side.
// Text PKs are caller-generated nanoids (event uses bigserial).

export const project = pgTable(
  "project",
  {
    id: text("id").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    repoOwner: text("repo_owner").notNull(),
    repoName: text("repo_name").notNull(),
    defaultBranch: text("default_branch").default("main").notNull(),
    webhookId: integer("webhook_id"), // GitHub hook id we created
    trainCommand: text("train_command").default("python train.py").notNull(),
    monitoringPrompt: text("monitoring_prompt"), // plain-English watch criteria
    fixingPrompt: text("fixing_prompt"), // hypothesis-agent prompt override
    confidenceThreshold: real("confidence_threshold").default(0.6).notNull(),
    maxAgents: integer("max_agents").default(3).notNull(),
    monitorModel: text("monitor_model")
      .default("wandb/microsoft/Phi-4-mini-instruct")
      .notNull(),
    trainingApiKey: text("training_api_key"), // raw ka_live_ key for sandbox runs
    status: text("status").default("idle").notNull(), // idle|training|incident|fixing|recovered|stopped
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => [index("project_user_id_idx").on(table.userId)],
)

export const run = pgTable(
  "run",
  {
    // library-chosen id: wandb run id, else nanoid
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    wandbRunId: text("wandb_run_id"),
    wandbUrl: text("wandb_url"),
    commitSha: text("commit_sha"),
    branch: text("branch"),
    source: text("source").default("local").notNull(), // local|sandbox
    sandboxId: text("sandbox_id"), // W&B sandbox id when source=sandbox
    status: text("status").default("training").notNull(), // training|incident|fixing|recovered|stopped|finished
    currentStep: integer("current_step"),
    latestLoss: real("latest_loss"),
    lossHistory: jsonb("loss_history"), // [{step,loss}] capped ~120
    metricsWindow: jsonb("metrics_window"), // [{step, metrics:{...}}] capped ~40
    demoMode: boolean("demo_mode").default(false),
    lastEventAt: timestamp("last_event_at"),
    lastScoredAt: timestamp("last_scored_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => [index("run_project_id_idx").on(table.projectId)],
)

export const incident = pgTable(
  "incident",
  {
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    runId: text("run_id")
      .notNull()
      .references(() => run.id, { onDelete: "cascade" }),
    kind: text("kind"), // nan_loss|divergence|stall|oom|exception|monitor_flag
    step: integer("step"),
    status: text("status").default("detected").notNull(), // detected|hypothesizing|fixing|resolved|failed
    confidence: real("confidence"), // monitor score that tripped it
    reasoning: text("reasoning"), // monitor's one-liner
    diagnosis: text("diagnosis"), // hypothesis agent's summary
    workflowRunId: text("workflow_run_id"), // Workflow DevKit run id
    weaveUrl: text("weave_url"),
    winnerAgentId: text("winner_agent_id"),
    resolvedAt: timestamp("resolved_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => [index("incident_project_id_idx").on(table.projectId)],
)

export const agent = pgTable(
  "agent",
  {
    id: text("id").primaryKey(),
    incidentId: text("incident_id")
      .notNull()
      .references(() => incident.id, { onDelete: "cascade" }),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    hypothesis: text("hypothesis").notNull(),
    branch: text("branch"), // keepalive/fix-{incidentShort}-{n}
    prUrl: text("pr_url"),
    prNumber: integer("pr_number"),
    state: text("state").default("spawned").notNull(), // spawned|coding|pushed|pr_opened|failed
    report: text("report"), // markdown report (also the PR body)
    sandboxId: text("sandbox_id"),
    error: text("error"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().notNull(),
  },
  (table) => [
    index("agent_incident_id_idx").on(table.incidentId),
    index("agent_project_id_idx").on(table.projectId),
  ],
)

export const event = pgTable(
  "event",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    projectId: text("project_id").notNull(),
    runId: text("run_id"),
    incidentId: text("incident_id"),
    agentId: text("agent_id"),
    source: text("source").notNull(), // library|server|monitor|hypothesis|coder|sandbox|github
    level: text("level").default("info").notNull(), // info|warn|error
    type: text("type").notNull(),
    message: text("message").notNull(),
    data: jsonb("data"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => [
    index("event_project_id_id_idx").on(table.projectId, table.id),
    index("event_incident_id_idx").on(table.incidentId),
  ],
)

export const memory = pgTable(
  "memory",
  {
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    incidentId: text("incident_id"),
    kind: text("kind"), // failure kind
    summary: text("summary").notNull(), // what happened + winning fix
    resolution: text("resolution"), // what fixed it (PR link, hypothesis)
    data: jsonb("data"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => [index("memory_project_id_idx").on(table.projectId)],
)

export const command = pgTable(
  "command",
  {
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    type: text("type").notNull(),
    status: text("status").default("pending").notNull(),
    consumedAt: timestamp("consumed_at"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
  },
  (table) => [
    index("command_project_id_status_idx").on(table.projectId, table.status),
  ],
)

export const schema = {
  user,
  session,
  account,
  verification,
  apikey,
  project,
  run,
  incident,
  agent,
  event,
  memory,
  command,
}
