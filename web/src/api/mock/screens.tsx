import { deferredScreen } from './DeferredScreen';

export const DemoLab = deferredScreen('Contract Playground', () => import('./lab/Lab'));
export const DemoKnowledge = deferredScreen('Knowledge Journal', () => import('../preview/journal/Journal'));
export const DemoComparison = deferredScreen('Invocation comparison', () => import('../preview/investigation/Comparison'));
export const DemoEvidence = deferredScreen('Evidence inspection', () => import('../preview/evidence/Reader'));
export const DemoExecution = deferredScreen('Recorded execution', () => import('../preview/execution/Recorder'));
