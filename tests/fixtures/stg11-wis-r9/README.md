# The store-group reference model (STG-11, A-36)

The work-item fact issuer's adopted amendment (A-36, WIS issuer profile revision 9) comes with a reference model of
WIS-01a, the store's group, and of the store writers' group and modes: `verify_store_group.py`, with the outputs it
must produce in `store-group-cases.json`. It is a regression aid, not normative. AEW's predicate
(`aew.engine.store_group`) must give the model's answer on every host it builds, and
`tests/integration/test_store_group.py` checks that.

**These files are not byte-identical to the adopted ones.** They are a whole-token rename of the model's synthetic
operator name, done by a script kept with the adoption record, outside this repository. Nothing else differs, and the
renamed model passes all of its own checks against the renamed cases and regenerates them byte for byte.

| File | Adopted source (A-36), SHA-256 | This copy, SHA-256 |
|---|---|---|
| `verify_store_group.py` | `c02538e957b3c0fb46db62d1bddec0e5cc9429d6d2f3547c9500ee00f8ad5849` | `251aac38075878fc15df00f5a0188dd3d04321a8838e99458a60549d2e140df3` |
| `store-group-cases.json` | `221688a3d8d793f1562eafb5f2ccceaca8a461d92989d2897b251e3f44819bea` | the same (it holds no renamed token) |

`tests/integration/test_store_group.py` pins this copy's hashes, runs the model (`python -I -B verify_store_group.py`,
103 named checks), and compares its answers with AEW's. Never edit these files by hand: regenerate them from the adopted
copy with the rename script.
