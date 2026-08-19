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
}

/** Simulated latency so loading/skeleton states are exercised in fixture mode. */
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

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
};

export const stackGraphClient: StackGraphClient = isFixtureMode() ? fixtureClient : liveClient;
