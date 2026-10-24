# Saved Configuration Contract

## Scope and selection

The title bar manages named snapshots within the current Mower instance. The
working paths remain `config/` and `tmp/`; saved snapshots live in
`config-profiles/`, outside exported configuration. Existing installations begin
with their current files as the default configuration.

Creating a configuration starts with defaults and inherits only the selected
groups from the current configuration. Copying uses the same operation with all
groups initially selected. ZIP import starts with the archive and retains only
the selected groups from the current configuration. Activation starts with the
saved target and retains the selected current groups. The result becomes the
target configuration's saved content, rather than a temporary display override.

Device and game connection parameters form one indivisible group. Other groups
separate runtime settings, daily tasks, MAA settings, long tasks, accounts,
notifications, appearance, remaining Mower settings, normal staffing, rescue
staffing, weekly plans, inventory, growth plans and history. The backend owns
group membership and supplies labels and descriptions to the frontend. Unknown
configuration fields and database tables have an explicit fallback group.
Recycling history keeps collection records, upload progress and the reporting
identity together, so activation preserves submitted prefixes and retry state.

Process access settings, the manager-owned assistant switch, network settings,
window state and saved scheduling state are not selectable. Local access settings
remain in place and saved scheduling state is cleared after successful activation.

## Atomic activation

**Selected Configuration Isolation**: A successful operation combines precisely
the selected groups, saves the outgoing configuration, applies the result, and
commits the active identifier and generation together. Missing data in an incoming
group clears that group's previous content. Other instances and unrelated
temporary files remain unchanged. File, database or metadata failure restores the
previous files, database and active metadata before publishing runtime objects.

SQLite is restored through its backup API. Partial database selection retains
whole tables, including their schema, according to their owning data group.
Archive limits and ten-second database deadlines follow the
[configuration backup contract](config-backup.md). Snapshots have opaque
identifiers, bounded names and a bounded configuration count; user input never
forms a filesystem path.

Activation and creation require idle scheduling, device operations, performance
tests, update jobs, assistant messages, recycling reports and shutdown state.
An active recycling report also blocks ordinary backup import until its upload
and progress commit finish. These operations use the existing configuration and
maintenance lock order. The generation is checked inside
the same serialization boundary as saves and activation. Requests from a previous generation are
rejected before changing files or starting work.

Each `/ws/chat` message carries the page's `generation`. The backend checks it
and registers the active message under the configuration serialization lock
before calling the model. Profile activation and the existing backup import remain
unavailable until that message's model and tool execution finishes, fails or
disconnects. An idle chat connection does not block activation. A stale message receives
`code=configuration_changed` and its connection closes before model dispatch;
a missing generation is accepted only while the current generation is `0`.

## Frontend boundary

The menu lists configurations and provides create, copy, rename, ZIP import and
ZIP export. Selection trees support parent selection and independent children.
Confirmation states that selected current content is written into the target
and that unapplied editor drafts are discarded.

Before activation, the frontend pauses and drains configuration, normal-plan and
initialized rescue-plan saves. It keeps old stores paused after success and
refreshes the current address with a one-use automatic-start suppression flag.
An uncertain transport result keeps saving paused until the server's generation
is verified or the page is refreshed. Renaming does not activate a configuration.

## API and verification

`GET /config-profiles` returns the active identifier, generation, list, selectable
groups and busy state. `POST /config-profiles` accepts `name` and `inherit` group
keys and creates and activates in one operation. `POST /config-profiles/import`
accepts multipart `backup`, `name` and a JSON-encoded `keep` list.
`POST /config-profiles/<id>/activate` accepts `keep`; `PATCH /config-profiles/<id>`
accepts a new `name`. `GET /config-profiles/export` returns the full backup ZIP
with only the selected weekly-plan key added as configuration metadata.

Profile writes require the access token, `X-Mower-Settings: 1` and the current
`X-Mower-Config-Generation` header. Other state-changing requests and task startup
also check the generation under the serialization lock. A missing generation is
accepted for legacy clients only before the first activation, when the generation
is `0`. After activation, a missing or old generation returns HTTP 409 with
`configuration_changed`; clients reload before submitting more work. A malformed
registry refuses writes instead of falling back to an unprotected generation.

Existing backup imports retain their compatibility behavior for missing tmp
files. Successful profile activation additionally clears prior runtime feedback
and workshop observations; failed activation retains those observations.

Focused offline tests exercise group selection, independent data round trips,
stale-generation rejection, running-state refusal and rollback after metadata
failure. Frontend checks cover grouped controls, all save queues, uncertain
responses and refresh suppression. These checks do not establish real-device
operation.
