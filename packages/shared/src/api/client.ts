// StackGraph read-API client with a pluggable transport.
//
//   fixtures  → resolves from bundled contracts/v1 fixtures (no backend required)
//   live      → fetches /api/v1/* from the real API
//
// Components depend ONLY on this interface, so flipping NEXT_PUBLIC_DATA_SOURCE
// requires no component rewrite. Fixture-first, per plan §7.1.

import { config, isFixtureMode } from "../config";
import type {
  ApplicationDetail,
  AskRequest,
  AskResponse,
  EstateSummary,
  EvidenceDetail,
  GraphNeighborhood,
  IdentityReviewRequest,
  IdentityReviewResult,
  CapabilityTaxonomy,
  RepositoryCapabilityIntelligence,
  OptimisticReviewRequest,
  CapabilityInferenceReviewResult,
  DuplicateCapabilityReviewResult,
  RepositoryModernizationIntelligence,
  ModernizationCandidateReviewResult,
  ModernizationRecommendationReviewRequest,
  ModernizationRecommendationReviewResult,
  ModernizationValidationOutcomeRequest,
  ModernizationValidationOutcomeResult,
  Phase3IntelligenceMetrics,
  ModernizationList,
  TechnologyDetail,
  BusinessMapList,
  BusinessMapDetail,
  BusinessMapSummary,
  BusinessMapCreateRequest,
  BusinessMapSaveRequest,
  BusinessMapRevisionList,
  SessionInfo,
  ReviewQueue,
  ReviewQueueItemType,
  TenantMemberList,
  TenantMember,
  MemberInviteRequest,
  MemberUpdateRequest,
  ConnectorList,
  Connector,
  ConnectorRegisterRequest,
  GitHubRepositoryConnectRequest,
  GitHubInstallationConnectRequest,
  ConnectorUpdateRequest,
  AIProviderConfiguration,
  AIProviderConfigurationUpdateRequest,
  AIProviderConnectionTest,
  ScanPolicy,
  ScanPolicyUpdateRequest,
  ScanStatus,
  ServiceStatusList,
  RescanRequest,
  RescanJob,
  RescanJobList,
  Namespace,
} from "../contracts/read-models";

// UI-demo estate (several ranked items across domains) so filter/sort/lens UI is exercisable.
// The golden fixture is contracts/v1/fixtures/estate-summary.json.
import estateSummary from "../fixtures/estate-summary.demo.json";
import applicationDetail from "../fixtures/application-detail.json";
import technologyDetail from "../fixtures/technology-detail.json";
import modernizationList from "../fixtures/modernization-list.json";
import askResponse from "../fixtures/ask-response.json";
// UI-demo neighborhood (richer than the golden fixture) so the uncertain-bridge and
// aggregate-cluster UI can be exercised in fixture mode. See the file's _comment.
import graphNeighborhood from "../fixtures/graph-neighborhood.demo.json";
import evidenceDetail from "../fixtures/evidence-detail.json";
import identityReview from "../fixtures/identity-review-result.json";
import capabilityTaxonomy from "../fixtures/capability-taxonomy.json";
import repositoryCapabilities from "../fixtures/repository-capabilities.json";
import repositoryModernization from "../fixtures/repository-modernization-intelligence.json";
import phase3Metrics from "../fixtures/phase3-intelligence-metrics.json";
import businessMapDetail from "../fixtures/business-map-detail.json";

export interface EstateSummaryParams {
  cursor?: string;
  limit?: number;
  domains?: Namespace[];
}

export interface StackGraphClient {
  getEstateSummary(params?: EstateSummaryParams): Promise<EstateSummary>;
  getApplication(id: string): Promise<ApplicationDetail>;
  getTechnology(id: string): Promise<TechnologyDetail>;
  listModernization(): Promise<ModernizationList>;
  ask(body: AskRequest): Promise<AskResponse>;
  getGraphNeighborhood(centerId: string, depth?: number): Promise<GraphNeighborhood>;
  getFactEvidence(factId: string): Promise<EvidenceDetail>;
  reviewIdentityAssertion(id: string, body: IdentityReviewRequest): Promise<IdentityReviewResult>;
  getCapabilityTaxonomy(version?: string): Promise<CapabilityTaxonomy>;
  getRepositoryCapabilities(id: string): Promise<RepositoryCapabilityIntelligence>;
  reviewCapabilityInference(id: string, body: OptimisticReviewRequest): Promise<CapabilityInferenceReviewResult>;
  reviewDuplicateCapabilityCandidate(id: string, body: OptimisticReviewRequest): Promise<DuplicateCapabilityReviewResult>;
  getRepositoryModernizationIntelligence(id: string, limit?: number): Promise<RepositoryModernizationIntelligence>;
  reviewModernizationCandidate(id: string, body: OptimisticReviewRequest): Promise<ModernizationCandidateReviewResult>;
  reviewModernizationRecommendation(id: string, body: ModernizationRecommendationReviewRequest): Promise<ModernizationRecommendationReviewResult>;
  recordModernizationValidationOutcome(id: string, body: ModernizationValidationOutcomeRequest): Promise<ModernizationValidationOutcomeResult>;
  getPhase3IntelligenceMetrics(): Promise<Phase3IntelligenceMetrics>;
  listBusinessMaps(cursor?: string, limit?: number): Promise<BusinessMapList>;
  createBusinessMap(body: BusinessMapCreateRequest): Promise<BusinessMapDetail>;
  getBusinessMap(id: string): Promise<BusinessMapDetail>;
  saveBusinessMap(id: string, body: BusinessMapSaveRequest): Promise<BusinessMapDetail>;
  archiveBusinessMap(id: string): Promise<BusinessMapSummary>;
  getBusinessMapRevisions(id: string): Promise<BusinessMapRevisionList>;
  getSession(): Promise<SessionInfo>;
  getReviewQueue(params?: {
    types?: ReviewQueueItemType[];
    repository?: string;
    cursor?: string;
    limit?: number;
  }): Promise<ReviewQueue>;
  listMembers(): Promise<TenantMemberList>;
  inviteMember(body: MemberInviteRequest): Promise<TenantMember>;
  updateMember(id: string, body: MemberUpdateRequest): Promise<TenantMember>;
  removeMember(id: string): Promise<TenantMember>;
  listConnectors(): Promise<ConnectorList>;
  registerConnector(body: ConnectorRegisterRequest): Promise<Connector>;
  connectGitHubRepository(body: GitHubRepositoryConnectRequest): Promise<Connector>;
  connectGitHubInstallation(body: GitHubInstallationConnectRequest): Promise<Connector>;
  updateConnector(id: string, body: ConnectorUpdateRequest): Promise<Connector>;
  removeConnector(id: string): Promise<Connector>;
  getAIProviderConfiguration(): Promise<AIProviderConfiguration>;
  updateAIProviderConfiguration(body: AIProviderConfigurationUpdateRequest): Promise<AIProviderConfiguration>;
  removeAIProviderKey(): Promise<AIProviderConfiguration>;
  testAIProviderConnection(): Promise<AIProviderConnectionTest>;
  getScanPolicy(): Promise<ScanPolicy>;
  updateScanPolicy(body: ScanPolicyUpdateRequest): Promise<ScanPolicy>;
  getScanStatus(): Promise<ScanStatus>;
  getServiceStatus(): Promise<ServiceStatusList>;
  requestRescan(body: RescanRequest): Promise<RescanJob>;
  listRescans(cursor?: string, limit?: number): Promise<RescanJobList>;
}

/** Simulated latency so loading/skeleton states are exercised in fixture mode. */
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

// Fixture mode keeps the Business Map in memory so the workspace's create/save/list flow is
// fully exercisable without a backend. It mirrors the server's optimistic-concurrency contract.
class FixtureApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`StackGraph API ${status}`);
    this.name = "ApiRequestError";
  }
}
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

// Fixture-mode admin state so the Admin surface's CRUD is exercisable without a backend.
// Seeded to mirror the previous mock sections so the demo looks unchanged on first load.
const adminMembers = new Map<string, TenantMember>();
const adminConnectors = new Map<string, Connector>();
const adminRescans = new Map<string, { idempotencyKey: string; job: RescanJob }>();
let adminScanPolicy: ScanPolicy = { contract_version: "1.0.0", cadence: "DAILY", enabled: true };
let adminAIConfiguration: AIProviderConfiguration = {
  contract_version: "1.0.0", provider: "anthropic", model: "", enabled: true,
  key_configured: false, test_status: "NOT_TESTED", enrichment_status: "DISABLED",
  pending_enrichment_jobs: 0, running_enrichment_jobs: 0, failed_enrichment_jobs: 0,
};
{
  const now = "2026-08-19T12:00:00.000Z";
  for (const seed of [
    { actor_key: "hariganesh@msn.com", display_name: "You", role: "admin", status: "ACTIVE" },
    { actor_key: "dana@acme.example", display_name: "Dana Okafor", role: "execute", status: "ACTIVE" },
    { actor_key: "priya@acme.example", display_name: "Priya Raman", role: "review", status: "ACTIVE" },
    { actor_key: "sam@acme.example", display_name: "Sam Lee", role: "view", status: "ACTIVE" },
  ] as const) {
    const id = `seed-${seed.actor_key}`;
    adminMembers.set(id, {
      id, actor_key: seed.actor_key, display_name: seed.display_name, email: seed.actor_key,
      role: seed.role, status: seed.status, created_at: now, updated_at: now,
    });
  }
  for (const seed of [
    { provider: "GITHUB_APP", display_name: "acme-corp (GitHub org)", scopes: ["repo:read", "metadata:read"], status: "CONNECTED" },
    { provider: "PACKAGE_REGISTRY", display_name: "npm-public", scopes: ["PUBLIC"], status: "CONNECTED" },
    { provider: "PACKAGE_REGISTRY", display_name: "artifactory-internal", scopes: ["PRIVATE"], status: "NEEDS_REAUTH" },
  ] as const) {
    const id = `seed-${seed.display_name}`;
    adminConnectors.set(id, {
      id, provider: seed.provider, display_name: seed.display_name, external_account_key: "",
      scopes: [...seed.scopes], status: seed.status, created_at: now, updated_at: now,
    });
  }
}
const businessMaps = new Map<string, BusinessMapDetail>();
const businessMapRevisions = new Map<string, BusinessMapRevisionList["revisions"]>();
{
  const seed = clone(businessMapDetail as BusinessMapDetail);
  businessMaps.set(seed.id, seed);
  businessMapRevisions.set(seed.id, [
    { version: 1, actor_key: "fixture", created_at: seed.created_at },
  ]);
}
const summarize = (m: BusinessMapDetail): BusinessMapSummary => ({
  id: m.id,
  map_key: m.map_key,
  title: m.state.title,
  view_mode: m.state.view_mode,
  template_id: m.state.template_id,
  status: m.status,
  version: m.version,
  created_at: m.created_at,
  updated_at: m.updated_at,
});

const fixtureClient: StackGraphClient = {
  async getEstateSummary(params) {
    await delay();
    const summary = clone(estateSummary as EstateSummary);
    if (params?.domains?.length) {
      summary.ranked_items = summary.ranked_items.filter((item) =>
        params.domains?.includes(item.domain),
      );
    }
    if (params?.limit) summary.ranked_items = summary.ranked_items.slice(0, params.limit);
    summary.page_info = { has_next_page: false };
    return summary;
  },
  async getApplication() {
    await delay();
    return applicationDetail as ApplicationDetail;
  },
  async getTechnology() {
    await delay();
    return technologyDetail as TechnologyDetail;
  },
  async listModernization() {
    await delay();
    return modernizationList as ModernizationList;
  },
  async ask() {
    await delay(300);
    return askResponse as AskResponse;
  },
  async getGraphNeighborhood() {
    await delay();
    return graphNeighborhood as GraphNeighborhood;
  },
  async getFactEvidence() {
    await delay();
    return evidenceDetail as EvidenceDetail;
  },
  async reviewIdentityAssertion() {
    await delay();
    return identityReview as IdentityReviewResult;
  },
  async getCapabilityTaxonomy() {
    await delay();
    return capabilityTaxonomy as CapabilityTaxonomy;
  },
  async getRepositoryCapabilities() {
    await delay();
    return repositoryCapabilities as RepositoryCapabilityIntelligence;
  },
  async reviewCapabilityInference(id, body) {
    await delay();
    return {contract_version: "1.0.0", capability_inference_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async reviewDuplicateCapabilityCandidate(id, body) {
    await delay();
    return {contract_version: "1.0.0", duplicate_capability_candidate_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async getRepositoryModernizationIntelligence() {
    await delay();
    return repositoryModernization as RepositoryModernizationIntelligence;
  },
  async reviewModernizationCandidate(id, body) {
    await delay();
    return {contract_version: "1.0.0", modernization_candidate_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async reviewModernizationRecommendation(id, body) {
    await delay();
    return {contract_version: "1.0.0", modernization_recommendation_id: id, review_state: body.decision === "ACCEPT" ? "ACCEPTED" : body.decision === "REJECT" ? "REJECTED" : "DISMISSED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async recordModernizationValidationOutcome(id, body) {
    await delay();
    return {contract_version: "1.0.0", id: "00000000-0000-4000-8000-000000000799", modernization_recommendation_id: id, validation_status: body.validation_status, reported_at: new Date().toISOString()};
  },
  async getPhase3IntelligenceMetrics() {
    await delay();
    return phase3Metrics as Phase3IntelligenceMetrics;
  },
  async listBusinessMaps() {
    await delay();
    const maps = [...businessMaps.values()]
      .filter((m) => m.status !== "ARCHIVED")
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map(summarize);
    return { contract_version: "1.0.0", as_of: new Date().toISOString(), maps, page_info: { has_next_page: false } };
  },
  async createBusinessMap(body) {
    await delay();
    for (const existing of businessMaps.values()) {
      if (existing.map_key === body.map_key) {
        throw new FixtureApiError(409, { code: "BUSINESS_MAP_EXISTS", map_key: body.map_key });
      }
    }
    const now = new Date().toISOString();
    const id = (globalThis.crypto?.randomUUID?.() ?? `fixture-${businessMaps.size + 1}`);
    const detail: BusinessMapDetail = {
      contract_version: "1.0.0", id, map_key: body.map_key, status: "ACTIVE", version: 1,
      created_at: now, updated_at: now, state: clone(body.state),
    };
    businessMaps.set(id, detail);
    businessMapRevisions.set(id, [{ version: 1, actor_key: "fixture", created_at: now }]);
    return clone(detail);
  },
  async getBusinessMap(id) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    return clone(detail);
  },
  async saveBusinessMap(id, body) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    if (detail.status === "ARCHIVED") throw new FixtureApiError(409, { code: "BUSINESS_MAP_ARCHIVED" });
    if (detail.version !== body.expected_version) {
      throw new FixtureApiError(409, {
        code: "VERSION_CONFLICT", expected_version: body.expected_version, actual_version: detail.version,
      });
    }
    const now = new Date().toISOString();
    const next: BusinessMapDetail = { ...detail, version: detail.version + 1, updated_at: now, state: clone(body.state) };
    businessMaps.set(id, next);
    businessMapRevisions.get(id)?.unshift({ version: next.version, actor_key: "fixture", created_at: now });
    return clone(next);
  },
  async archiveBusinessMap(id) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    detail.status = "ARCHIVED";
    detail.updated_at = new Date().toISOString();
    return summarize(detail);
  },
  async getBusinessMapRevisions(id) {
    await delay();
    if (!businessMaps.has(id)) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    return { contract_version: "1.0.0", business_map_id: id, revisions: clone(businessMapRevisions.get(id) ?? []) };
  },
  async getSession() {
    await delay();
    // Fixture/demo runs as a full-capability admin so every surface is exercisable.
    return { contract_version: "1.0.0", actor_key: "fixture-admin", tenant_id: null, capabilities: ["admin"] };
  },
  async getReviewQueue() {
    await delay();
    const now = new Date().toISOString();
    return {
      contract_version: "1.0.0",
      as_of: now,
      counts: {
        IDENTITY_ASSERTION: 1, CAPABILITY_INFERENCE: 0, DUPLICATE_CAPABILITY: 0,
        MODERNIZATION_CANDIDATE: 0, MODERNIZATION_RECOMMENDATION: 0,
      },
      items: [{
        item_id: "00000000-0000-4000-8000-000000000501",
        item_type: "IDENTITY_ASSERTION", review_state: "POSSIBLE",
        title: "stripe ↔ stripe-node", confidence: 0.72, confidence_band: "MEDIUM",
        version: 1, created_at: now,
        review_path: "/identity-assertions/00000000-0000-4000-8000-000000000501/review",
      }],
      page_info: { has_next_page: false },
    };
  },
  async listMembers() {
    await delay();
    return { contract_version: "1.0.0", members: clone([...adminMembers.values()]) };
  },
  async inviteMember(body) {
    await delay();
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `member-${adminMembers.size + 1}`;
    const member: TenantMember = {
      id, actor_key: body.actor_key, display_name: body.display_name ?? "",
      email: body.email ?? "", role: body.role ?? "view", status: "INVITED",
      created_at: now, updated_at: now,
    };
    adminMembers.set(id, member);
    return clone(member);
  },
  async updateMember(id, body) {
    await delay();
    const member = adminMembers.get(id);
    if (!member) throw new FixtureApiError(404, { code: "MEMBER_NOT_FOUND" });
    if (body.role) member.role = body.role;
    if (body.status) member.status = body.status;
    member.updated_at = new Date().toISOString();
    return clone(member);
  },
  async removeMember(id) {
    await delay();
    const member = adminMembers.get(id);
    if (!member) throw new FixtureApiError(404, { code: "MEMBER_NOT_FOUND" });
    adminMembers.delete(id);
    return clone(member);
  },
  async listConnectors() {
    await delay();
    return { contract_version: "1.0.0", connectors: clone([...adminConnectors.values()]) };
  },
  async registerConnector(body) {
    await delay();
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `connector-${adminConnectors.size + 1}`;
    const connector: Connector = {
      id, provider: body.provider, display_name: body.display_name,
      external_account_key: body.external_account_key ?? "", scopes: body.scopes ?? [],
      status: "CONNECTED", created_at: now, updated_at: now,
    };
    adminConnectors.set(id, connector);
    return clone(connector);
  },
  async connectGitHubRepository(body) {
    return this.registerConnector({
      provider: "GITHUB_APP",
      display_name: body.repository,
      external_account_key: `github:repository:${body.repository.toLowerCase()}`,
      credential_reference: body.credential_reference ?? "env://GITHUB_TOKEN",
      scopes: ["contents:read", "metadata:read"],
    });
  },
  async connectGitHubInstallation(body) {
    return this.registerConnector({
      provider: "GITHUB_APP",
      display_name: body.display_name ?? `GitHub installation ${body.installation_id}`,
      external_account_key: `github:installation:${body.installation_id}`,
      credential_reference: `github-app://installation/${body.installation_id}`,
      scopes: ["contents:read", "metadata:read"],
    });
  },
  async updateConnector(id, body) {
    await delay();
    const connector = adminConnectors.get(id);
    if (!connector) throw new FixtureApiError(404, { code: "CONNECTOR_NOT_FOUND" });
    if (body.display_name) connector.display_name = body.display_name;
    if (body.status) connector.status = body.status;
    if (body.scopes) connector.scopes = body.scopes;
    connector.updated_at = new Date().toISOString();
    return clone(connector);
  },
  async removeConnector(id) {
    await delay();
    const connector = adminConnectors.get(id);
    if (!connector) throw new FixtureApiError(404, { code: "CONNECTOR_NOT_FOUND" });
    adminConnectors.delete(id);
    return clone(connector);
  },
  async getAIProviderConfiguration() {
    await delay();
    return clone(adminAIConfiguration);
  },
  async updateAIProviderConfiguration(body) {
    await delay();
    adminAIConfiguration = {
      ...adminAIConfiguration,
      provider: body.provider,
      model: body.model ?? "",
      enabled: body.enabled ?? true,
      key_configured: body.api_key ? true : adminAIConfiguration.key_configured,
      key_fingerprint: body.api_key ? body.api_key.slice(-4) : adminAIConfiguration.key_fingerprint,
      test_status: "NOT_TESTED",
      enrichment_status: body.enabled !== false && Boolean(body.model) && Boolean(body.api_key || adminAIConfiguration.key_configured)
        ? "READY" : "DISABLED",
      pending_enrichment_jobs: 0,
      running_enrichment_jobs: 0,
      failed_enrichment_jobs: 0,
      last_enrichment_at: null,
      tested_at: null,
      last_error: null,
      updated_by: "fixture-admin",
      updated_at: new Date().toISOString(),
    };
    return clone(adminAIConfiguration);
  },
  async removeAIProviderKey() {
    await delay();
    adminAIConfiguration = {
      ...adminAIConfiguration, key_configured: false, key_fingerprint: null,
      test_status: "NOT_TESTED", tested_at: null, last_error: null,
      enrichment_status: "DISABLED", pending_enrichment_jobs: 0,
      running_enrichment_jobs: 0, failed_enrichment_jobs: 0, last_enrichment_at: null,
    };
    return clone(adminAIConfiguration);
  },
  async testAIProviderConnection() {
    await delay();
    if (!adminAIConfiguration.key_configured) {
      throw new FixtureApiError(422, { message: "Save a provider API key before testing the connection." });
    }
    adminAIConfiguration = {
      ...adminAIConfiguration, test_status: "SUCCEEDED", tested_at: new Date().toISOString(), last_error: null,
    };
    return { contract_version: "1.0.0", provider: adminAIConfiguration.provider, status: "SUCCEEDED", models: [] };
  },
  async getScanPolicy() {
    await delay();
    return clone(adminScanPolicy);
  },
  async updateScanPolicy(body) {
    await delay();
    adminScanPolicy = {
      contract_version: "1.0.0", cadence: body.cadence, enabled: body.enabled ?? true,
      updated_by: "fixture-admin", updated_at: new Date().toISOString(),
    };
    return clone(adminScanPolicy);
  },
  async getScanStatus() {
    await delay();
    return {
      contract_version: "1.0.0", as_of: new Date().toISOString(), policy: clone(adminScanPolicy),
      quotas: [
        { provider: "GITHUB_APP", used: 4200, limit: 5000, status: "OK", observed_at: new Date().toISOString() },
      ],
      recent_jobs: clone([...adminRescans.values()].map((r) => r.job).slice(-10).reverse()),
    };
  },
  async getServiceStatus() {
    await delay();
    const now = new Date().toISOString();
    return {
      contract_version: "1.0.0", as_of: now,
      services: [
        ["web", "Web UI", "CORE"], ["api", "API", "CORE"],
        ["database", "PostgreSQL / AGE", "CORE"],
        ["github-webhook", "GitHub webhooks", "INGESTION"],
        ["github-control-loop", "GitHub discovery", "INGESTION"],
        ["depsdev", "deps.dev enrichment", "ENRICHMENT"],
        ["osv", "OSV vulnerability enrichment", "ENRICHMENT"],
        ["projection", "Graph projection", "GRAPH"],
        ["intelligence", "Modernization intelligence", "INTELLIGENCE"],
      ].map(([key, name, category]) => ({
        key, name, category: category as ServiceStatusList["services"][number]["category"],
        state: "IDLE" as const, detail: "Worker is online and the durable queue is clear.",
        configured: true, pending: 0, running: 0, failed: 0,
        last_heartbeat_at: now,
      })),
    };
  },
  async requestRescan(body) {
    await delay();
    const existing = [...adminRescans.values()].find((j) => j.idempotencyKey === body.idempotency_key);
    if (existing) return clone(existing.job);
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `rescan-${adminRescans.size + 1}`;
    const job: RescanJob = {
      id, connector_id: body.connector_id ?? null, status: "PENDING",
      reason: body.reason ?? "", requested_by: "fixture-admin", created_at: now,
    };
    adminRescans.set(id, { idempotencyKey: body.idempotency_key, job });
    return clone(job);
  },
  async listRescans() {
    await delay();
    return {
      contract_version: "1.0.0",
      jobs: clone([...adminRescans.values()].map((r) => r.job).reverse()),
      page_info: { has_next_page: false },
    };
  },
};

async function req<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    // Tenant comes from the session cookie, never a client-supplied field (contract §31 / plan §7).
    credentials: "include",
  });
  if (res.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    const refreshed = await fetch(`${config.apiBaseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (refreshed.ok) return req<T>(path, init, false);
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = { message: res.statusText };
    }
    throw new ApiRequestError(res.status, detail);
  }
  return (await res.json()) as T;
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`StackGraph API ${status}`);
    this.name = "ApiRequestError";
  }
}

const liveClient: StackGraphClient = {
  getEstateSummary: (params) => {
    const query = new URLSearchParams();
    if (params?.cursor) query.set("cursor", params.cursor);
    if (params?.limit) query.set("limit", String(params.limit));
    for (const domain of params?.domains ?? []) query.append("domain", domain);
    const suffix = query.size ? `?${query.toString()}` : "";
    return req(`/estate/summary${suffix}`);
  },
  getApplication: (id) => req(`/applications/${id}`),
  getTechnology: (id) => req(`/technologies/${id}`),
  listModernization: () => req("/modernization"),
  ask: (body) => req("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getGraphNeighborhood: (centerId, depth = 1) =>
    req(`/graph/neighborhood?center_id=${encodeURIComponent(centerId)}&depth=${depth}`),
  getFactEvidence: (factId) => req(`/facts/${factId}/evidence`),
  reviewIdentityAssertion: (id, body) =>
    req(`/identity-assertions/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getCapabilityTaxonomy: (version) =>
    req(`/capabilities/taxonomy${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  getRepositoryCapabilities: (id) => req(`/repositories/${id}/capabilities`),
  reviewCapabilityInference: (id, body) =>
    req(`/capability-inferences/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  reviewDuplicateCapabilityCandidate: (id, body) =>
    req(`/duplicate-capability-candidates/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getRepositoryModernizationIntelligence: (id, limit = 50) =>
    req(`/repositories/${id}/modernization-intelligence?limit=${limit}`),
  reviewModernizationCandidate: (id, body) =>
    req(`/modernization-candidates/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  reviewModernizationRecommendation: (id, body) =>
    req(`/modernization-recommendations/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  recordModernizationValidationOutcome: (id, body) =>
    req(`/modernization-recommendations/${id}/validation-outcomes`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getPhase3IntelligenceMetrics: () => req("/intelligence/phase-3/metrics"),
  listBusinessMaps: (cursor, limit = 50) =>
    req(`/business-maps?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  createBusinessMap: (body) =>
    req("/business-maps", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getBusinessMap: (id) => req(`/business-maps/${id}`),
  saveBusinessMap: (id, body) =>
    req(`/business-maps/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  archiveBusinessMap: (id) => req(`/business-maps/${id}`, { method: "DELETE" }),
  getBusinessMapRevisions: (id) => req(`/business-maps/${id}/revisions`),
  getSession: () => req("/session"),
  getReviewQueue: (params) => {
    const search = new URLSearchParams();
    for (const type of params?.types ?? []) search.append("type", type);
    if (params?.repository) search.set("repository", params.repository);
    if (params?.cursor) search.set("cursor", params.cursor);
    if (params?.limit != null) search.set("limit", String(params.limit));
    const query = search.toString();
    return req(`/reviews/queue${query ? `?${query}` : ""}`);
  },
  listMembers: () => req("/admin/members"),
  inviteMember: (body) =>
    req("/admin/members", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateMember: (id, body) =>
    req(`/admin/members/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeMember: (id) => req(`/admin/members/${id}`, { method: "DELETE" }),
  listConnectors: () => req("/admin/connectors"),
  registerConnector: (body) =>
    req("/admin/connectors", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  connectGitHubRepository: (body) =>
    req("/admin/github/repositories", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  connectGitHubInstallation: (body) =>
    req("/admin/github/installations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateConnector: (id, body) =>
    req(`/admin/connectors/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeConnector: (id) => req(`/admin/connectors/${id}`, { method: "DELETE" }),
  getAIProviderConfiguration: () => req("/admin/ai-configuration"),
  updateAIProviderConfiguration: (body) =>
    req("/admin/ai-configuration", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeAIProviderKey: () => req("/admin/ai-configuration/key", { method: "DELETE" }),
  testAIProviderConnection: () => req("/admin/ai-configuration/test", { method: "POST" }),
  getScanPolicy: () => req("/admin/scan-policy"),
  updateScanPolicy: (body) =>
    req("/admin/scan-policy", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getScanStatus: () => req("/admin/scan-status"),
  getServiceStatus: () => req("/admin/services"),
  requestRescan: (body) =>
    req("/admin/rescans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listRescans: (cursor, limit = 50) =>
    req(`/admin/rescans?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
};

export const stackGraphClient: StackGraphClient = isFixtureMode() ? fixtureClient : liveClient;
