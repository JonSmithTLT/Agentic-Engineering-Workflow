import { deferredScreen } from './DeferredScreen';

const loadLab = () => import('./lab/Lab');
const loadKnowledge = () => import('../preview/journal/Journal');
const loadComparison = () => import('../preview/investigation/Comparison');
const loadEvidence = () => import('../preview/evidence/Reader');
const loadExecution = () => import('../preview/execution/Recorder');

const screens = {
  DemoLab: deferredScreen('Contract Playground', loadLab),
  DemoKnowledge: deferredScreen('Knowledge Journal', loadKnowledge),
  DemoComparison: deferredScreen('Invocation comparison', loadComparison),
  DemoEvidence: deferredScreen('Evidence inspection', loadEvidence),
  DemoExecution: deferredScreen('Recorded execution', loadExecution),
};

// Preserve initial deep-link readiness: do not add a Suspense reveal waterfall
// in front of the requested screen's existing project/detail loading states.
// Later navigation still loads its requested screen inside the visible shell.
export async function initialScreens(pathname: string) {
  const initial = { ...screens };
  try {
    switch (pathname.replace(/\/+$/, '')) {
      case '/knowledge': initial.DemoKnowledge = (await loadKnowledge()).default; break;
      case '/compare': initial.DemoComparison = (await loadComparison()).default; break;
      case '/evidence/inspect': initial.DemoEvidence = (await loadEvidence()).default; break;
      case '/execution': initial.DemoExecution = (await loadExecution()).default; break;
    }
  } catch {
    // Keep the deferred boundary so a failed initial import has an explicit
    // reload result rather than rejecting startup and hiding the whole shell.
  }
  return initial;
}
