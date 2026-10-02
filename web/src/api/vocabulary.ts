/** Known values from the C0 main-line review at 91c0d98. Wire strings stay open. */
export const ticketStates = [
  'BLOCKED',
  'READY',
  'ASSIGNED',
  'RUNNING',
  'REVIEW_PENDING',
  'REVIEW_FAILED',
  'REVIEW_PASSED',
  'VERIFY_PENDING',
  'VERIFICATION_FAILED',
  'VERIFICATION_INCONCLUSIVE',
  'VERIFIED',
  'COMMIT_READY',
  'DONE',
  'INTERRUPTED',
  'REPLAN_REQUIRED',
  'ESCALATED',
  'CANCELLED',
] as const;
export const parentStates = [
  'PLANNING',
  'IN_PROGRESS',
  'ACCEPTANCE_PENDING',
  'DONE',
  'CANCELLED',
] as const;
export const workStates = [...ticketStates, ...parentStates] as const;
export const invocationStatuses = [
  'active',
  'completed',
  'cancelled',
  'interrupted',
  'revoked',
  'superseded',
] as const;
export const invocationRoles = [
  'implementer',
  'reviewer',
  'verifier',
  'planner',
  'investigator',
  'researcher',
] as const;
export const harnessStatuses = [
  'starting',
  'running',
  'launch_failed',
  'ended_with_evidence',
  'ended_without_evidence',
  'crashed',
  'terminated',
  'unconfirmed',
] as const;
export const evidenceKinds = [
  'implementation_report',
  'review',
  'verification',
  'check_result',
  'discovery_record',
  'research_record',
  'plan_proposal',
] as const;
export const evidenceResults = [
  'pass',
  'fail',
  'inconclusive',
  'blocked',
] as const;
export const evidenceCurrentness = ['CURRENT', 'STALE', 'UNKNOWN'] as const;
export const decisionTypes = [
  'verification_failure_classification',
  'authority_transfer',
  'authority_acceptance',
  'authority_rejection',
  'waiver',
  'manifest_adoption',
  'state_regression',
  'cancellation',
  'reconciliation',
  'plan_acceptance',
  'promotion',
  'role_plan_change',
  'closeout',
  'evidence_acceptance',
  'hierarchy_change',
  'dependency_change',
  'plan_reconfirmation',
  'input_acknowledgement',
  'attempt_supersession',
] as const;
export const historyKinds = [
  'unit',
  'annotation',
  'audit',
  'lead',
] as const;
export const trustSources = [
  'engine',
  'operator',
  'model',
  'external',
] as const;
export const annotationRelations = [
  'moved_to',
  'superseded_by',
  'promoted_to',
  'lineage',
  'audit_finding',
] as const;
