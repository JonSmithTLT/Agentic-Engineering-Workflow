/** Pinned Engine evidence; no browser classification or fallback logic. */
export const vocabularyInventory = {
  engine_commit:'032140af8abf2738c770f4eb181ad6b6326a145d',
  sources:[
    {path:'src/aew/harness/containment/__init__.py',sha256:'4bf603b81f5d38909be748526e44c2b7e6de6d7d73d19d0b4ac0f2cfc6e84784'},
    {path:'src/aew/harness/containment/probe.py',sha256:'d8443f318c685db24f17c083a393fa353d010e2a04ffac557965178c7af99a8a'},
    {path:'src/aew/harness/contract.py',sha256:'14c1e9fe315488a5439fadb539bf18be5edd5d330fda9a4f71d70eb8e0eda789'},
  ],
  dimensions:{filesystem:['os_readonly_roots','workdir_separation_only'],process_ownership:['pid_namespace','job_object','process_group'],network:['not_provided']},
  self_test:['ok','reason'], mechanism:'Supplied Engine mechanism label, never inferred.',
  provisional:['configured/available/authorized/active projection','validation receipt identity/currentness/time','relation kinds','lane kinds','budget observations'],
  boundaries:['process_ownership is not process containment','os_readonly_roots is filesystem integrity, not confidentiality or network isolation','No browser fallback classification','New receipt/currentness metadata is PROVISIONAL, not M4-B authority'],
};
