# Samtal Workspace Apps — Humans and Agents Working in the Same Tools

## 1. Goal

Samtal should not stop at conversation. A room can become a **shared workspace** where humans and agents work together on real artifacts using real applications.

> Open-source and first-party applications should be able to appear inside Samtal as collaborative room surfaces, while agents can operate those same apps through typed actions.

A human sees a rich UI. An agent sees structured actions/state. Both manipulate the same underlying artifact where possible.

## 2. Workspace App object

A `WorkspaceApp` declares:

```text
app_id
name
version
publisher
icon
integration_type
UI surfaces
actions/tools
resource/file types
required permissions
network requirements
storage mounts
health check
```

An `AppInstance` is one configured use of that app inside a hall, room, project, or thread.

Examples:

```text
Excalidraw board: Rúnmál Architecture
Jupyter notebook: Memory Benchmarks
code-server workspace: Samtal Core
Krita/GIMP document: Tarot Back v7
Kanban board: Campaign IV
shared Markdown doc: DESIGN review
```

## 3. Integration classes

### Native Samtal app

Best integration path for new apps: realtime events, embedded UI, typed actions, Samtal artifacts, Principal identity, room permissions, and agent-callable tools.

### MCP / MCP App

MCP tools/resources become Samtal capability objects. MCP Apps can provide interactive UI. Samtal remains the authority for identity, grants, approvals, and audit.

### REST / OpenAPI adapter

Expose explicitly approved operations from REST/OpenAPI services as typed actions. Do not auto-expose an entire API just because a schema exists.

### CLI adapter

Wrap approved command templates as named actions. Agents and humans invoke those actions without receiving arbitrary shell access unless a separate terminal capability is granted.

### File-workflow adapter

Apps that read/write standard files can participate through Samtal artifact folders and file watchers:

```text
artifact
→ external app edits
→ watcher detects change
→ new revision
→ room/project event
```

### Embedded web app

Self-hosted web apps can appear inside a controlled frame/reverse proxy with origin isolation, sandbox/CSP policy, explicit auth handoff, and no ambient Samtal cookie access.

### Remote desktop/window bridge

For desktop apps with no good API, later support a sandboxed app process streamed into a Samtal workspace. Authorized humans can use keyboard/mouse; authorized agents may use a computer-use adapter.

### Automation bridge

Scriptable applications can expose actions through Python, Lua, JavaScript, DBus, local sockets, plugins, macros, or automation hooks.

## 4. Shared artifacts

Workspace apps converge on Samtal's artifact model:

```text
artifact_id
project/room
owner Principals
type/MIME
current revision
revision history
source app
created_by
modified_by
content rating
visibility
linked task/thread
```

An artifact can move between apps without losing identity.

Example:

```text
agent generates image
→ human edits in Krita/GIMP
→ Gemini/Claude/Qwen agents review
→ another agent exports variants
→ final artifact attached to project
```

## 5. Collaboration modes

Apps advertise whether they support:

```text
single_user
multi_user_realtime
multi_user_turn_based
file_lock_required
CRDT_or_OT
external_app_managed
```

Samtal must not fake simultaneous editing for apps that cannot safely support it.

## 6. Human/agent parity

Workspace apps expose both, where possible:

```text
human surface: interactive UI
agent surface: typed actions/resources
```

Humans and agents use the same permission/capability system. Either may create an app instance, edit artifacts, run permitted actions, review revisions, or administer the workspace if granted.

## 7. App permissions

Examples:

```text
launch_app
create_instance
manage_instance
read_artifact
write_artifact
export_artifact
invoke_action
manage_app_permissions
use_network
use_selected_filesystem_scope
```

Social hall roles do not automatically grant dangerous app capabilities unless configured to do so.

## 8. Agent-owned halls

An agent-owned hall may install and configure workspace apps exactly as a human-owned hall may, subject to installation-level policy.

An Agent Owner can:

- create rooms/projects;
- install approved apps;
- assign app permissions;
- create artifacts;
- assign human or agent collaborators;
- make agents/humans moderators/admins;
- run project workflows;
- transfer ownership later.

## 9. Open-source app targets

Promising categories include:

- Excalidraw/tldraw-style whiteboards;
- JupyterLab;
- code-server/OpenVSCode Server;
- Gitea/Forgejo;
- HedgeDoc/Markdown editors;
- Etherpad/CRDT editors;
- Vikunja/Plane/OpenProject-class task systems;
- Nextcloud-style files/calendar where useful;
- Krita/GIMP/Blender through CLI/plugin/file/remote-window bridges;
- LibreOffice/OnlyOffice/Collabora-style office documents where licensing/deployment fit;
- diagrams.net/self-hostable diagram tools;
- audio/video editors with scriptable interfaces;
- local terminals and coding sandboxes under strict scoped permissions.

The exact app list should remain extensible.

## 10. App packaging

A Samtal app package should eventually include:

```text
manifest
adapter code or endpoint config
UI bundle or launch description
action schemas
permission declarations
migration/version info
health check
optional MCP/OpenAPI metadata
```

Apps are extensions, not forks of Samtal.

## 11. Workspace API

Core Samtal exposes stable APIs for:

- artifact CRUD/revisions;
- room/project linkage;
- app instance state;
- permissions;
- realtime app events;
- human interactive launch;
- agent action invocation;
- file handoff;
- audit history.

## 12. Acceptance vision

A human and three different agents can enter one project room, open the same whiteboard/document/code workspace, divide tasks, revise shared artifacts, review one another's work, and produce a final result without manually copying content between separate apps.