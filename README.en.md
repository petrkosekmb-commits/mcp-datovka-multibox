# Datovka Multibox

[Česky](README.cs.md) | [English](README.en.md)

## What it does

Datovka Multibox connects an AI assistant to multiple Czech government data
boxes (ISDS). It helps people managing personal and business correspondence
select the correct account, list messages, read received messages and
attachments, find recipients, and prepare replies with files. Sending requires
review of the exact draft in a local window. The connector only uses accounts
you configure and their existing permissions.

Based on [Sensio-cz/mcp-datovka](https://github.com/Sensio-cz/mcp-datovka).
See [UPSTREAM.md](UPSTREAM.md) for provenance. Version 0.2.0 has passed offline
tests; access to real ISDS accounts has not yet been verified. Start with the
ISDS test environment before production use.

## Public code and private installation

The public repository contains code, plugin manifests, documentation, tests and
fictional examples. The private installation uses the same code with your own
accounts, permissions and drafts. There is no branch containing passwords that
could accidentally be merged into public code.

On Windows, private files live in `%LOCALAPPDATA%\DatovkaMultibox`; elsewhere,
in `~/.local/share/DatovkaMultibox`. Override this with an absolute
`DATOVKA_PRIVATE_DIR` outside the repository. Passwords are stored separately
through keyring in the OS credential store, including Windows Credential Manager.
Drafts and attachments are in local SQLite without application-level encryption.
Protect your OS account and disk, and never publish the private directory.

## Install and configure

Requires Python 3.11 or newer. From the repository root on Windows:

```powershell
./scripts/install.ps1
./scripts/nastavit-ucet.ps1
```

The installer creates an isolated `.venv` and private settings. The account
wizard, currently in Czech, asks for an alias, box ID, ISDS username, environment
and separate receive/send permissions. Password input is hidden. Repeat it for
additional accounts. Adding an account does not contact ISDS or verify login.
Test is the default environment; production requires an explicit choice.

Only ISDS username/password authentication is currently implemented. Mobile Key,
bank identity, SMS and certificates are not supported by this version.

After installing the runtime, install the Codex plugin:

```powershell
codex plugin marketplace add petrkosekmb-commits/mcp-datovka-multibox
codex plugin add datovka-multibox@datovka-multibox-community
```

Open a new chat. The private `runtime.json` lets the cached plugin find its
runtime. Rerun `install.ps1` after source updates. GitHub publication does not
publish the plugin in the OpenAI directory.

Other MCP clients can use stdio with the absolute path to
`.venv/Scripts/python.exe` and arguments `-m mcp_datovka`.
On Linux use `python3 -m venv .venv`, then `.venv/bin/python -m pip install .`.
A working OS keyring and Tk are required for credentials and local review.

## Operations

| Tool | Purpose |
|---|---|
| `datovka_list_boxes` | List local accounts without contacting ISDS. |
| `datovka_list_received` | List incoming messages in the selected account. |
| `datovka_list_sent` | List outgoing messages in the selected account. |
| `datovka_read_message` | Download a received message and base64 attachments. |
| `datovka_search_box` | Find a recipient through an explicitly selected account. |
| `datovka_prepare_message` | Save an immutable draft without sending. |
| `datovka_get_draft` | Inspect full content, file hashes and state. |
| `datovka_send_draft` | Make one attempt to send a locally approved draft. |

The `files` JSON array accepts an absolute `file_path`, or `filename`,
`mime_type` and `content_base64`. File content is captured at preparation time;
changing the original file later does not change the draft. Body text becomes
`text-zpravy.txt`, including when other files are attached. The local limit is
20 MiB and 50 added attachments; this is not a claim about ISDS service limits.

## Review and send

1. Prepare a draft and check the sender, environment, recipient ID and content.
2. Open the local review window:

   ```powershell
   ./.venv/Scripts/python.exe -m mcp_datovka.setup review DRAFT_ID
   ```

3. The user approves that exact draft. Approval alone does not send it.
4. The assistant can call `datovka_send_draft` for the approved draft.

Drafts expire after 24 hours; approval lasts 15 minutes. Changed content or
sender configuration requires a new draft and approval. Before sending, the
connector checks that the authenticated box matches the configured sender.
Only one attempt is allowed, including concurrent calls.

`sent` means ISDS returned a message ID, not that the recipient received it.
An `uncertain` result or a `sending` state after a crash requires checking sent
messages. Never automatically create a new draft to retry. No MCP tool grants
approval. This protects the MCP interface, not against programs with full access
to the same local files or desktop input.

## Delivery effects and privacy

Fetching incoming messages can trigger legal delivery and response periods.
Disabling sending alone does not prevent this; receiving is enabled separately.
There is no automatic synchronization scheduler. See the
[Datovka manual](https://www.datovka.cz/datovka-docs/datovka/manual).

Content returned to the AI client may be processed by its provider according to
client settings. A local connector does not guarantee that content remains on
the computer. ZFO archiving, delivery receipt archiving and automatic NAS backup
are not implemented in this version.

## Development

```powershell
./.venv/Scripts/python.exe -m pip install pytest build setuptools wheel
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m build --wheel
```

Tests use fictional accounts and block network requests. They cover account
selection, permissions, immutable drafts, approval expiry, concurrency,
uncertain outcomes, ISDS errors and attachments. CI runs on Windows and Linux.
Passing these tests is not proof of live ISDS compatibility.

## Support development

If my adaptations and maintenance help you, you can support this derivative on
[Buy Me a Coffee](https://buymeacoffee.com/kojakcio). Contributions are optional
and not required to use the project. Sensio.cz created the original project;
this link supports the maintainer of the derivative.

Original code: MIT, see LICENSE. See UPSTREAM.md for inherited WSDL/XSD
provenance and dependency licensing.
