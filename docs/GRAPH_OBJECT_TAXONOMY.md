# ChronoSpear Graph / Memory Object Taxonomy

This document exists so future agents do not mistake "graph-addressable" for "same kind of thing."

## Implemented in Slice 1

### 🟢 Identity Node

Enduring addressable thing/concept known to CAM.

Current Identity families:

- **Entity** — enduring actors/things/concepts that participate in world meaning.
- **Place** — enduring place identity; map/location relationships are not embedded here.
- **Describer** — enduring descriptive/type concept used by associative reasoning.

Shape:

`IdentityId + Name + IdentityKind + Description`

### Relationship Type

Controlled semantic vocabulary. ChronoSpear's locked core is:

- `IS_A`
- `MEMBER_OF`
- `PART_OF`
- `LOCATED_IN`
- `BASED_IN`
- `OWNS`
- `OPPOSES`

`RelationshipVocabulary.core()` returns a fresh vocabulary containing exactly this core. Additional relationship semantics remain explicit extensions rather than silently inferred durable vocabulary.

Relationship Type is **not a Node**.

### Association

Addressable directed semantic assertion:

`AssociationId: SourceIdentity --RELATIONSHIP_TYPE--> TargetIdentity`

It is not an anonymous edge and not an Identity Node.

### WorldTime

Continuous world coordinate. Answers: **when did this happen/apply in the represented world?**

### SystemTime

Monotonic acquisition/revision coordinate. Answers: **when did ChronoSpear learn/accept this information?**

### ChronoStamp

Immutable captured pair:

`ChronoStamp(WorldTime, SystemTime)`

A stamp is not a clock owner. It prevents ambiguous duplicated raw integer time fields while preserving the two distinct coordinates. Multiple records may legitimately carry/reference equal coordinate values; the rule is one authoritative clock meaning, not object interning.

---

## Implemented in Slice 2

### 🔵 Historical Occurrence

Immutable graph-addressable record representing something that happened.

Shape:

`OccurrenceId + ChronoStamp + one-or-more Entity participant IdentityIds + required Place IdentityId + synopsis + story`

Historical Occurrences preserve world History. Every participant must resolve to an Entity Identity; Place and Describer identities are rejected as participants. The required `place` must resolve to a Place Identity. Historical Occurrences are not Identity Nodes and not Associations. Slice 2 deliberately adds no recall, Association provenance, lifecycle, correction, persistence, or semantic event deduplication.

---

## Known families deliberately NOT implemented yet

### 🟡 Amend Node

Historical corrective/additional information attached to an occurrence. Part of VARA.

### 🔴 Void Node

Historical invalidation attached to an occurrence for effective canonical reads. Part of VARA.

### 🟠 Audit Note

Persistent local diagnostic record describing destructive/plastic changes to CAM's own carried knowledge. Audit history is not world history and stays out of ordinary recall.

### 🟣 Calendar Node

Provisional specialized temporal-knowledge concepts used to interpret raw WorldTime (calendar, month, era, season, holiday, etc.). Do not create one node per tick/date. Calendar meaning is not WorldTime itself.

### 🗣️ Language Node / Language Surface

Experimentally proven semantic access mechanism. Natural-language forms activate controlled CAM semantic targets. Language does not carry mutable world truth.

Language access must eventually be able to target more than Identity Nodes, for example Relationship Types and Associations, without granting an LLM raw graph access.

### Historical Support

Provenance binding an Association to one or more Historical Occurrences. Multiple supports may sustain one Association.

### Lifecycle Episode

Temporal episode for one semantic Association. Query-time resolver eventually yields FUTURE / EFFECTIVE / ENDED. Lifecycle is not permanent mutable status.

### Perspective Knowledge / KNOWS

Addressable epistemic relation indicating what a perspective knows. Exact assertion knowledge targets Association IDs, not vague endpoint proximity.

### Interaction Log Entry

Persistent raw conversation/action record. Answers **what was said**, not **what happened**. A future action may receive an ST-bounded recent window while still starting a fresh provider conversation.

---

## Do not flatten these distinctions

```text
Identity Node       != Historical Occurrence
Identity Node       != Association
Historical Occurrence != Association
Relationship Type   != Node
Language Surface    != world truth
WorldTime           != Calendar meaning
WorldTime           != SystemTime
ChronoStamp         != clock authority
Audit               != World History
Interaction Log     != World History
LLM result          != persistent truth
```
