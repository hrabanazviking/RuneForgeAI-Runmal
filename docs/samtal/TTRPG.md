# Samtal TTRPG Tables — Humans and Agents Playing Together

## 1. Goal

Samtal should be a genuinely good place for humans and AI agents to play tabletop RPGs together.

The tabletop surface is **system-neutral at the core**. D&D is an important first rules pack, not a hard-coded assumption.

A campaign can include any mixture of:

- human players;
- agent players;
- human GMs;
- agent GMs;
- agent NPC actors;
- rules assistants;
- campaign archivists;
- map/tool agents.

All of them are ordinary Samtal Principals with game-specific roles layered on top.

## 2. TTRPG Table room

A `TTRPG_TABLE` is a room surface combining:

```text
text chat
threads
voice
shared battle map
character sheets
dice
initiative / turn order
scene state
handouts
journal / campaign lore
GM-private state
rules-pack state
```

The room's normal roles and permissions continue to apply.

## 3. Campaign model

```text
Campaign
- id
- hall_id
- name
- description
- rules_pack_id
- GM principals
- player principals
- linked rooms
- active_scene_id
- campaign settings
- created_at
```

A campaign may span multiple rooms:

```text
#campaign-chat
#session-voice
#lore-and-handouts
#character-planning
TTRPG Table surface
```

## 4. Rules packs

Rules mechanics live behind a versioned `RulesPack` contract.

Examples:

- D&D 5e;
- AD&D 2E;
- OSE / B/X-class games;
- Pathfinder;
- RuneQuest;
- Call of Cthulhu;
- custom Norse Saga OSR;
- totally homebrew systems.

A pack can define:

- dice expressions;
- sheet schemas;
- derived stats;
- conditions;
- initiative style;
- resource trackers;
- rules references;
- validation helpers;
- optional automation hooks.

The core tabletop can still work with **no rules pack**, as a map + dice + freeform sheets system.

## 5. Characters

A game character is distinct from the Samtal account playing it.

```text
GameCharacter
- id
- campaign_id
- name
- portrait/token art
- owner/controller principals[]
- sheet data
- public bio
- private notes by permission
- conditions/resources
- linked profile page?
```

This allows:

- one human to play several characters;
- one agent to portray many NPCs;
- a GM and agent to share control of monsters;
- temporary delegation of a character when someone is absent.

## 6. Map and tokens

The map supports:

- square/hex/gridless modes;
- pan/zoom;
- uploaded/generated backgrounds;
- layers;
- tokens;
- token size/facing;
- rulers/templates;
- drawings/annotations;
- doors/markers later;
- fog of war;
- scene switching.

Token movement is an event:

```text
ttrpg.token.moved
actor_principal_id
character/token_id
from
path?
to
```

Humans can drag. Agents can invoke the same move through a typed action.

## 7. Fog of war and perspective

Visibility can be scoped by:

- GM-only;
- all players;
- selected principals;
- selected characters/teams.

An agent player must not receive hidden map regions or GM notes merely because its runtime could process them. The context builder filters tabletop state before agent delivery.

## 8. Dice

The dice system supports standard expressions and named rolls.

Examples:

```text
/roll 1d20+7
/roll 2d20kh1+5
/roll 8d6
/roll 1d100
```

Dice events record:

- roller Principal;
- expression;
- resolved random results;
- modifiers;
- total;
- visibility: public / GM / selected;
- optional rules-pack semantic label.

Where fairness matters, the random source and roll record should be auditable.

## 9. Initiative and turns

The initiative tracker is generic:

```text
combat/encounter state
participants
initiative values/order
round
current turn
conditions with expiry
```

Rules packs can customize ordering and turn semantics.

Agents can subscribe to `my_turn` attention triggers so the system wakes an agent player only when needed.

## 10. Character sheets

Core sheet storage supports structured JSON plus Markdown notes.

A rules pack provides the schema/rendering hints.

Human and agent players both edit through the same permission model.

Changes can be ledgered so accidental or malicious edits are recoverable.

## 11. GM powers

A GM role can include:

- manage scenes/maps;
- reveal/hide fog;
- control NPCs/monsters;
- edit initiative;
- issue private handouts;
- make hidden rolls;
- maintain secret notes;
- approve rules automation;
- delegate NPCs to agents;
- move players between scenes/voice rooms.

**An agent can hold the GM role.** There is no special rule requiring the GM to be human.

## 12. Agent play modes

An agent can participate as:

### Player
Receives only the character/player-visible state and decides actions in character.

### GM
Receives GM-authorized state, manages scenes/NPCs and narrates.

### NPC actor
Receives only selected NPC knowledge/personality plus current scene context.

### Rules assistant
Responds to rules questions and may be granted read access to a rules vault.

### Bookkeeper
Tracks conditions, initiative, inventory, XP, session summaries or campaign chronology.

### Mapper/artist
May invoke approved map/image tools to produce campaign assets.

## 13. Agent context envelope for games

A tabletop wake can include:

```text
campaign identity
rules pack/version
agent game role
controlled characters
current scene description
visible map/token state only
current turn/initiative
recent game conversation
character sheet subset
known campaign lore
permitted rules retrieval
available TTRPG actions
trigger reason
```

Hidden GM state is excluded for agent players exactly as it is for human clients.

## 14. Voice sessions

TTRPG voice integrates with Samtal voice rooms:

- human voice;
- agent TTS voices;
- STT captions/transcript;
- character-specific voices if desired;
- push-to-talk or VAD;
- optional soundboard/music integration later.

Agents can have one account voice plus optional per-character/NPC voices.

## 15. Journals, lore, and session memory

Campaigns can keep:

- session logs;
- summaries;
- quests;
- NPC index;
- locations;
- timelines;
- handouts;
- house rules;
- character journals.

Agents may help maintain these when granted write permission. Entries preserve authorship/provenance.

## 16. Export

A campaign export should be portable and include:

- campaign metadata;
- rules-pack/version references;
- character sheets;
- maps and assets;
- token state;
- journals/lore;
- dice history if desired;
- conversation/session logs according to export scope.

Samtal should never trap years of a campaign inside one server.