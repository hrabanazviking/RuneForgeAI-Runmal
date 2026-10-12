# Samtal Permissions, Vaults, Tools & Approval Plane

## 1. Two permission systems, deliberately separate

Samtal distinguishes:

1. **Social permissions** — what a Principal may do inside Samtal.
2. **Capability permissions** — what external data/tools/actions a Principal may use.

A Moderator who can delete spam does not automatically gain filesystem access. An agent with a Photoshop/GIMP plugin does not automatically gain moderation powers.

## 2. Social permissions

These come from hall roles and channel/category overrides.

Examples:

```text
manage_hall
manage_roles
manage_rooms
manage_invites
view_audit_log
kick_members
ban_members
timeout_members
manage_messages
manage_threads
send_messages
attach_files
create_threads
mention_everyone
connect_voice
speak_voice
manage_voice
manage_events
manage_ttrpg_table
```

The resolver is Principal-neutral. Human and Agent principals use the same permission engine.

## 3. Capability grants

A capability grant is an explicit statement such as:

```text
principal X may READ vault Y
principal X may CALL plugin Z action create_image
principal X may WRITE project folder /foo/bar
principal X may POST through connector Q only to account A
```

A grant has:

```text
principal_id or role_id
resource_type
resource_id
allowed_actions[]
scope constraints
created_by
created_at
expires_at?
approval_policy?
```

## 4. Vault permissions

Vault level:

```text
none
read
write
admin
```

`read` permits retrieval but not mutation.

`write` permits adding/updating content according to vault policy.

`admin` permits changing vault membership/metadata and grants where policy allows.

Every retrieval/write remains attributable.

## 5. Plugin/action permissions

Permissions apply at the action level where useful.

Example:

```text
GIMP
  open_image       ALLOW
  transform_image  ALLOW
  export_file      ALLOW selected directory
  run_arbitrary_script DENY

Gmail-style connector
  search/read      ALLOW
  draft            ALLOW
  send             REQUIRE_APPROVAL
```

The plugin manifest advertises actions and schemas; Samtal owns authorization above the plugin.

## 6. Human and agent equality

Capability rules do not assume agents are the only tool users.

A human Principal can invoke a Samtal plugin from the UI or slash/action command if granted.

An agent can do the same through its context/tool interface.

The same audit and approval system applies.

## 7. Approval policies

A grant/action may be:

```text
ALLOW
DENY
REQUIRE_APPROVAL_ALWAYS
REQUIRE_APPROVAL_FIRST_TIME
REQUIRE_APPROVAL_ABOVE_THRESHOLD
```

Approval can be delegated to particular roles/Principals.

The tool request becomes a durable object so approval can happen asynchronously.

## 8. Tool invocation lifecycle

```text
requested
policy_evaluated
waiting_approval?
approved/denied
started
progress?
completed/failed/cancelled
```

Room-visible summaries may be posted without leaking secrets or giant raw outputs.

## 9. MCP integration

MCP is a strong interoperability layer for tools/resources/prompts. Current official MCP SDK documentation describes tools, resources and prompts as first-class server features and the stable v2 SDK line implements the 2026-07-28 protocol revision.

Samtal can act as:

- an MCP host/client for tool servers;
- a provider of Samtal resources/actions to agents;
- an application host for MCP Apps where appropriate.

But Samtal's capability grants, hall identity and audit remain the source of authority. Connecting an MCP server does not grant every agent every tool.

## 10. First-party ecosystem apps

RuneForgeAI systems can register as plugins/adapters:

- Rúnmál;
- Aesir;
- HugrGate;
- Mythic Coder/forge coding systems;
- Aurelia;
- astrology engine;
- tarot engine;
- Norse Saga Engine;
- kiosk/display tools;
- future projects.

Each gets a manifest and permission surface rather than privileged hidden access.

## 11. External apps

Any scriptable external application can potentially receive an adapter:

- GIMP;
- Blender;
- Git;
- local CLIs;
- IDEs;
- browsers through bounded automation;
- media tools;
- game servers;
- smart-home/local devices.

Adapters should run least-privilege with filesystem/network/resource scopes.

## 12. Audit ledger

Record at least:

```text
who requested
who executed
which plugin/action/resource
when
permission decision
approver if any
sanitized input summary/result summary
success/failure
linked room/task
```

Raw secrets never enter the ledger.

## 13. Permission inspection UX

Every Principal should be able to answer:

- What rooms can I see?
- What roles do I have?
- What can I moderate?
- What vaults can I read/write?
- What apps/tools can I use?
- Which actions require approval?
- What permissions did I grant to this agent?

For agents, the context envelope can include a machine-readable effective capability summary.

## 14. Revocation

Role changes and capability revocation take effect immediately for new actions.

Long-running tasks receive a cancellation/revocation signal when technically possible.

A disconnected agent cannot retain a stale bearer of authority forever; credential/session design must support expiry/rotation.