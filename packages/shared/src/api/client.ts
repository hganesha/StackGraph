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

export interface StackGraphClient {
  getEstateSummary(): Promise<EstateSummary>;
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
  async getEstateSummary() {
    await delay();
    return estateSummary as EstateSummary;
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
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    // Tenant comes from the session cookie, never a client-supplied field (contract §31 / plan §7).
    credentials: "include",
  });
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
  getEstateSummary: () => req("/estate/summary"),
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
};

export const stackGraphClient: StackGraphClient = isFixtureMode() ? fixtureClient : liveClient;
