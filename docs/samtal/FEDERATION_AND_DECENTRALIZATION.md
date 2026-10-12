# Samtal Federation & Decentralization

## 1. Principle

Samtal should work beautifully as one private self-hosted hall before federation exists.

Federation is for linking sovereign halls without creating one central company-owned network.

## 2. What federation means

Two Samtal nodes may choose to share:

- room membership;
- remote Principals;
- room events;
- selected profile data;
- media references/copies;
- federation presence where supported;
- invites/joins;
- room state.

A local hall decides what it federates.

## 3. Matrix lessons

Matrix is worth studying closely because its official specification models open decentralized communication using users, devices, typed events, rooms, room state and server-to-server federation.

Useful ideas to learn from:

- typed events;
- opaque IDs;
- room-scoped state;
- signed server-to-server exchange;
- backfill/history synchronization;
- endpoint/protocol versioning;
- custom event namespaces.

Samtal should not automatically inherit Matrix's full room-state-resolution complexity unless its own federation requirements justify it.

Official spec: https://spec.matrix.org/

## 4. Samtal federation identity

Each node has a stable server/federation identity with signing keys.

Remote identities are namespaced/qualified so collisions cannot occur.

Conceptually:

```text
local Principal: p_01...
remote Principal: qualified remote identity + cached local mapping
```

UI can still show friendly handles.

## 5. Signed events/requests

Federation messages use authenticated server-to-server requests with:

- sender server;
- timestamp/nonce;
- request/event hash;
- signature;
- protocol version.

Receiving servers validate schema, signature, authorization and local policy before accepting data.

## 6. Local supremacy

Remote role claims do not grant local admin/tool authority.

A remote Principal may be given a local hall role, but that mapping is a local decision.

A remote hall cannot force local content policy, capability grants, moderation or plugin access.

## 7. Profile federation

Profiles can publish selected fields as `federated-public`.

Private/contacts/hall-only profile sections never become federated merely because the account has a DID.

Large media can be copied/proxied according to storage/privacy policy.

## 8. DIDs

W3C DID Core v1.0 is a Recommendation; DID Core v1.1 is in the 2026 standards process.

Samtal may allow a Principal or server to bind a DID as an additional cryptographic identity proof.

DID is **optional**.

A local Samtal username remains enough to use Samtal.

Official W3C source: https://www.w3.org/TR/did-core/

## 9. Wallets

Wallet-based login/proof may be supported as one authentication option.

Samtal does not require:

- cryptocurrency;
- token ownership;
- gas fees;
- NFTs;
- a public blockchain.

“Web3-native” here means decentralized identity/ownership/interoperability can be first-class without turning basic chat into a financial transaction.

## 10. Hall discovery

Public/federated halls may publish discovery metadata:

```text
hall name
server
summary
icon
public rooms
joining policy
supported protocol version
```

Private halls expose nothing unless explicitly configured.

## 11. Remote agent discovery

A federated Agent Principal may expose a public agent profile and optionally A2A discovery metadata.

Samtal can bridge remote task collaboration through A2A without making A2A responsible for the entire room/social protocol.

## 12. Media federation

Media has:

- immutable hash/content ID;
- origin;
- MIME/type metadata;
- rating/visibility metadata;
- access policy.

Local servers may proxy/cache permitted remote media.

Content-rating preferences remain local and are enforced before display/delivery.

## 13. Blocking servers

Node administrators can:

- block a remote server entirely;
- block a remote Principal;
- stop federating a specific room;
- reject remote media;
- rate-limit peers.

## 14. Federation roadmap rule

Do not start serious federation implementation until:

- local rooms/messages are stable;
- IDs/event versioning are stable;
- permission semantics are defined;
- export/backup works;
- one-node Samtal is genuinely useful.

Federation built on unstable local semantics would fossilize mistakes.