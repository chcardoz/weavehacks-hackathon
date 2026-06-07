import {
  bigserial,
  boolean,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
} from "drizzle-orm/pg-core"

export const user = pgTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified")
    .$defaultFn(() => false)
    .notNull(),
  image: text("image"),
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

// --- observability tables (see infra/observability.md for the contract) ---

export const project = pgTable("project", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  repo: text("repo"),
  wandbRunId: text("wandb_run_id"),
  wandbUrl: text("wandb_url"),
  commitSha: text("commit_sha"),
  status: text("status")
    .$defaultFn(() => "training")
    .notNull(),
  currentStep: integer("current_step"),
  latestLoss: doublePrecision("latest_loss"),
  lossHistory: jsonb("loss_history"),
  demoMode: boolean("demo_mode").$defaultFn(() => false),
  apikeyId: text("apikey_id"),
  lastEventAt: timestamp("last_event_at"),
  createdAt: timestamp("created_at")
    .$defaultFn(() => new Date())
    .notNull(),
  updatedAt: timestamp("updated_at")
    .$defaultFn(() => new Date())
    .notNull(),
})

export const incident = pgTable(
  "incident",
  {
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    kind: text("kind").notNull(),
    step: integer("step"),
    status: text("status")
      .$defaultFn(() => "detected")
      .notNull(),
    diagnosis: text("diagnosis"),
    humanReply: text("human_reply"),
    deadlineAt: timestamp("deadline_at"),
    weaveUrl: text("weave_url"),
    winnerAgentId: text("winner_agent_id"),
    resolvedAt: timestamp("resolved_at"),
    createdAt: timestamp("created_at")
      .$defaultFn(() => new Date())
      .notNull(),
    updatedAt: timestamp("updated_at")
      .$defaultFn(() => new Date())
      .notNull(),
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
    projectId: text("project_id").notNull(),
    hypothesis: text("hypothesis"),
    cursorAgentId: text("cursor_agent_id"),
    branch: text("branch"),
    state: text("state")
      .$defaultFn(() => "spawned")
      .notNull(),
    wandbRunId: text("wandb_run_id"),
    finalLoss: doublePrecision("final_loss"),
    lossHistory: jsonb("loss_history"),
    error: text("error"),
    createdAt: timestamp("created_at")
      .$defaultFn(() => new Date())
      .notNull(),
    updatedAt: timestamp("updated_at")
      .$defaultFn(() => new Date())
      .notNull(),
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
    incidentId: text("incident_id"),
    agentId: text("agent_id"),
    source: text("source").notNull(),
    level: text("level")
      .$defaultFn(() => "info")
      .notNull(),
    type: text("type").notNull(),
    message: text("message").notNull(),
    data: jsonb("data"),
    createdAt: timestamp("created_at")
      .$defaultFn(() => new Date())
      .notNull(),
  },
  (table) => [
    index("event_project_id_id_idx").on(table.projectId, table.id),
    index("event_incident_id_idx").on(table.incidentId),
  ],
)

export const command = pgTable(
  "command",
  {
    id: text("id").primaryKey(),
    projectId: text("project_id")
      .notNull()
      .references(() => project.id, { onDelete: "cascade" }),
    type: text("type").notNull(),
    status: text("status")
      .$defaultFn(() => "pending")
      .notNull(),
    consumedAt: timestamp("consumed_at"),
    createdAt: timestamp("created_at")
      .$defaultFn(() => new Date())
      .notNull(),
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
  incident,
  agent,
  event,
  command,
}
