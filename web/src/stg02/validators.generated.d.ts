type Validator = ((value: unknown) => boolean) & { errors?: { dataPath?: string; message?: string }[] | null };
export const validators: Record<'waiting' | 'run' | 'continuation' | 'operations' | 'd01Problem' | 'command' | 'receipt' | 'operation' | 'o01Problem', Validator>;
