CREATE TABLE ai_prompt_template (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  prompt_key text NOT NULL CHECK(prompt_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  version text NOT NULL CHECK(version ~ '^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$'),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  messages jsonb NOT NULL CHECK(jsonb_typeof(messages)='array' AND jsonb_array_length(messages)>0),
  input_variables text[] NOT NULL DEFAULT '{}',
  output_schema jsonb CHECK(output_schema IS NULL OR jsonb_typeof(output_schema)='object'),
  model_parameters jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(model_parameters)='object'),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,prompt_key,version)
);

CREATE UNIQUE INDEX uq_ai_prompt_active_global
  ON ai_prompt_template(prompt_key)
  WHERE tenant_id IS NULL AND status='ACTIVE';
CREATE UNIQUE INDEX uq_ai_prompt_active_tenant
  ON ai_prompt_template(tenant_id,prompt_key)
  WHERE tenant_id IS NOT NULL AND status='ACTIVE';
CREATE INDEX idx_ai_prompt_lookup
  ON ai_prompt_template(tenant_id,prompt_key,status,created_at DESC);

CREATE TABLE ai_model_invocation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  prompt_template_id uuid REFERENCES ai_prompt_template(id),
  prompt_key text NOT NULL CHECK(prompt_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  prompt_version text NOT NULL,
  prompt_content_hash text NOT NULL CHECK(prompt_content_hash ~ '^sha256:[a-f0-9]{64}$'),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  provider text NOT NULL,
  requested_model text NOT NULL,
  resolved_model text,
  provider_request_id text,
  policy_version text,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SUCCEEDED','FAILED','CANCELLED')),
  finish_reason text,
  input_tokens integer CHECK(input_tokens IS NULL OR input_tokens>=0),
  output_tokens integer CHECK(output_tokens IS NULL OR output_tokens>=0),
  total_tokens integer CHECK(total_tokens IS NULL OR total_tokens>=0),
  actual_cost_usd numeric(16,8) CHECK(actual_cost_usd IS NULL OR actual_cost_usd>=0),
  duration_ms integer CHECK(duration_ms IS NULL OR duration_ms>=0),
  error_code text,
  error_detail jsonb CHECK(error_detail IS NULL OR jsonb_typeof(error_detail)='object'),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX idx_ai_invocation_tenant_started
  ON ai_model_invocation(tenant_id,started_at DESC);
CREATE INDEX idx_ai_invocation_fingerprint
  ON ai_model_invocation(tenant_id,input_fingerprint,status);

ALTER TABLE ai_prompt_template ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON ai_prompt_template
  USING (tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());

ALTER TABLE ai_model_invocation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON ai_model_invocation
  USING (tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());
