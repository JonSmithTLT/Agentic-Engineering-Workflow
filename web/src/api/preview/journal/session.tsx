import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboard } from '../../../client/dashboard';
import { useReadSession } from '../../../client/queries';
import { ReadTransport } from '../../transport';
import { RequestLog } from '../../diagnostics';
import { journalContract } from './registration';
import { readClock } from '../../../client/clock';
const Context = createContext<ReadTransport | null>(null);
export function JournalSession({ name, children }: {
    name: string;
    children: ReactNode;
}) {
    const base = useReadSession(), project = useDashboard().project.data?.value.project_id;
    const client = useQueryClient();
    const reader = useMemo(() => {
        const r = new ReadTransport(undefined, () => readClock.now(), new RequestLog(), { base: '/api/preview/journal/v0.1', routes: /^\/entries(?:\/[A-Za-z0-9%._:-]+)?(?:\?|$)/ });
        r.reset({ ...base.identity, mode: 'demo', dataset: `${base.identity.dataset}:journal:${name}`, contract: `provisional:${journalContract.version}:${journalContract.sha256}` });
        if (project)
            r.context.bind(project);
        return r;
    }, [base, name, project]);
    useEffect(() => () => {
        reader.context.retire();
        const owned = (q: {
            queryKey: readonly unknown[];
        }) => q.queryKey[1] === reader.context.key('/entries');
        void client.cancelQueries({ predicate: owned });
        client.removeQueries({ predicate: owned });
    }, [reader, client]);
    if (!project)
        return <p role="status">Waiting for project bootstrap…</p>;
    return <Context.Provider value={reader}>{children}</Context.Provider>;
}
export function useJournalReader() {
    const reader = useContext(Context);
    if (!reader)
        throw new Error('Journal read context missing');
    return reader;
}
