-- The MCP server joins the workspace-controllable services in Admin -> Services & health.

ALTER TABLE tenant_service_control
  DROP CONSTRAINT tenant_service_control_service_key_check;
ALTER TABLE tenant_service_control
  ADD CONSTRAINT tenant_service_control_service_key_check
  CHECK(service_key IN (
    'github-webhook','github-control-loop','projection','intelligence','graph-intelligence','embeddings','mcp'
  ));

INSERT INTO tenant_service_control(tenant_id,service_key,desired_state,updated_by)
SELECT id,'mcp','RUNNING','migration-046' FROM tenant
ON CONFLICT(tenant_id,service_key) DO NOTHING;
