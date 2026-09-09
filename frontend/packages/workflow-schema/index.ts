/**
 * @fusion-flow/workflow-schema
 *
 * Placeholder package. Per the architecture plan (M5 — Workflow builder + execution
 * engine), this package will hold the Zod side of the shared node-config schema, mirroring
 * the backend's Pydantic `config_schema` per node type (trigger/action/condition), so the
 * `@xyflow/react` workflow builder in frontend/web can validate node configuration client-side
 * before publish (in addition to the backend's authoritative publish-time validation).
 *
 * The workspace/package entry exists now (empty) so that when M5 lands, the agent building
 * the workflow engine + builder UI does not need to restructure the workspace — it just fills
 * this file in and adds the corresponding node schemas.
 *
 * Nothing is exported yet.
 */

export const WORKFLOW_SCHEMA_PLACEHOLDER = true;
