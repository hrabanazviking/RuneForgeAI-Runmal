# Rúnmál Backup, Export and Recovery

Sovereignty means the user can move, restore and rebuild their digital life without depending on one provider, one machine or one database accident.

## 1. Three different operations

Do not conflate:

- **Backup** — faithful recovery of one Rúnmál installation/database.
- **Portable export** — provider/machine-independent user data intended to move between installations/versions.
- **Derived-state rebuild** — recreate vectors/indexes/summaries that can be regenerated from canonical source data.

## 2. SQLite backup

Do not teach users to blindly copy a live SQLite database while writes may be in flight. Use SQLite's supported online-backup mechanism or an equivalent checkpoint/snapshot procedure and verify the resulting file can be opened/integrity-checked.

A backup set records:

- application version;
- schema/migration version;
- creation timestamp;
- database checksum;
- asset directory/archive checksum if assets are external;
- whether secrets were included (ordinary portable backup/export: **no**).

## 3. Portable Rúnmál archive

Introduce a versioned portable bundle, provisionally `.runmal`.

Conceptual contents:

```text
manifest.json
characters/
chats/
lorebooks/
memories/
presets/
assets/
configuration/public-settings.json
```

Never include provider API keys, bearer tokens or bridge secrets.

The manifest declares archive format version, exported app version, checksums and capability/compatibility information.

## 4. Canonical vs derived data

Canonical portable data:

- character-card source data + Rúnmál metadata;
- messages/chat structure;
- lorebooks;
- user-authored presets/settings that are safe to export;
- memory statements + provenance + temporal state;
- supported assets.

Derived/rebuildable data may include:

- vector embeddings;
- FTS indexes;
- caches;
- latency metrics;
- temporary TTS/STT artifacts.

Portable archives may omit derived vectors and rebuild them against the target embedding backend.

## 5. Restore flow

1. Validate archive manifest/version/checksums.
2. Reject unsafe paths/oversized malformed archive members.
3. Import canonical data into a staging/new database.
4. Run required migrations.
5. Validate referential invariants.
6. Rebuild FTS/vector derived state as necessary.
7. Produce a restore report before swapping into active use.

Failed restore must not corrupt the currently working installation.

## 6. Disaster-recovery acceptance

The strongest release test is a clean-machine resurrection:

1. start from no Rúnmál state;
2. install released application;
3. restore a portable/backup artifact from the previous supported version;
4. open the same character and chat;
5. verify lore, messages, memories/provenance and assets;
6. rebuild embeddings using a possibly different compatible embedding provider;
7. successfully generate a new turn.

The provider is replaceable. The user's persistent state survives.

## 7. Retention

Recommended backup tooling may support rotating snapshots (for example recent daily + weekly checkpoints) but should not silently delete the user's only known-good backup.

## 8. Integrity tooling

`runmal doctor` should eventually be able to verify:

- SQLite integrity;
- migration/schema version;
- orphaned assets;
- broken provenance references;
- vector provenance consistency;
- archive checksums;
- missing configured models/providers/audio devices.

## 9. Privacy

Exports may contain extremely private conversation/memory data. Make their sensitivity explicit. No automatic cloud upload is part of core backup behavior.

## 10. Compatibility promise

Released archive formats are versioned. Rúnmál should either import an older supported archive or fail with a precise compatibility error and documented migration path, never silently discard unknown user data.

## 11. Sovereign resurrection (S808, proven)

The full claim is exercised end-to-end by `tests/test_s808_resurrection.py`: a complete world (persona + card + avatar bytes, lorebook, chat history, a memory statement with source and chunk provenance, a sampling preset) is exported from state dir A as a `.runmal` archive, imported into a clean state dir B, and its derived indexes are rebuilt under a *different* embedding profile. In B: persona, lore, and chat open byte-identical; the memory statement and its source link survive; embeddings are honestly re-declared under the new profile (the old space is destroyed, never mixed — INV-019); the memory is retrievable in the new space; and the resurrected chat continues with a new generated turn. Data is portable, restorable, and re-embeddable without the original provider — that is the sovereignty this campaign exists to prove.