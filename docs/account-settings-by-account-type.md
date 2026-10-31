# Account Settings by account type: Local Folders and POP versus IMAP and Exchange

Thunderbird shows different Account Settings pages and controls for different account types.
This document compares four types: Local Folders, POP, IMAP and Exchange (EWS). It is for KB
writers. An article that describes one account type can be wrong for another.

The facts come from the code and en-US strings of Thunderbird 160.0 beta, read on 2026-10-31
(sumo-linter #22). They are not from a manual check of the running app. The sources are listed
at the end.

## The short version

- Local Folders is not an email account. It has no server and no identities. It gets a
  special main page and no Server Settings page.
- POP downloads messages and then works locally. Its storage page is called **Disk Space**.
- IMAP and Exchange keep messages on the server and synchronize them. Their storage page is
  called **Synchronization & Storage**.

## Pages in the account tree

Each account in Account Settings has a list of pages under its name.

| Page | Local Folders | POP | IMAP | Exchange (EWS) |
|---|---|---|---|---|
| Main page (account name) | Special page, see below | Identity page | Identity page | Identity page |
| Server Settings | No | Yes | Yes | Yes |
| Copies & Folders | No | Yes | Yes | Yes |
| Composition & Addressing | No | Yes | Yes | Yes |
| Manage spam | Yes | Yes | Yes | Yes |
| Disk Space | Yes | Yes | No | No |
| Synchronization & Storage | No | No | Yes | Yes |
| End-To-End Encryption | No | Yes | Yes | Yes |
| Return Receipts | No | Yes | Yes | Yes |

The storage page is one page with two names. For an account that keeps a synchronized copy
of the server, Thunderbird calls it Synchronization & Storage. For other accounts, it calls it
Disk Space.
Exchange is a special case in the code: it always gets Synchronization & Storage.

Server Settings, Copies & Folders and Composition & Addressing appear only for an account that
has identities. Local Folders has none.

## Local Folders main page

Local Folders gets one page that replaces the main page and Server Settings. It says "The
following is a special account. There are no identities associated with it." It contains:

- Account Name and Color
- Message Storage: Empty Trash on Exit, Message Store Type (File per folder (mbox) or File per
  message (maildir)), and Local Directory

## Server Settings

POP, IMAP and Exchange share these controls:

- the server, security and sign-in fields
- the two "Check for new messages" settings, at startup and every … minutes
- Empty Trash on Exit

The other controls differ.

| Control | POP | IMAP | Exchange (EWS) |
|---|---|---|---|
| Get new messages when they arrive on the server | No | Yes | No |
| Automatically download new messages | Yes | No | No |
| Fetch headers only | Yes | No | No |
| Leave messages on server (for at most … days, until I delete them) | Yes | No | No |
| Deleting messages: Move it to this folder | No | Yes | Yes |
| Deleting messages: Mark as deleted without moving | No | Yes | No |
| Deleting messages: Delete immediately | No | Yes | Yes |
| Permanently remove deleted messages from the Inbox on exit | No | Yes | Yes |
| Advanced… | Yes | Yes | Yes |

The Advanced… button opens a different dialog for each type:

- POP: where new messages go. The account can keep its own Inbox, or use the Inbox of another
  account, for example the Local Folders global Inbox.
- IMAP: the server directory, subscription, the maximum number of server connections and the
  IMAP namespaces.
- Exchange: none of the POP or IMAP options. With an experimental preference on, the dialog
  shows OAuth override fields.

## Disk Space and Synchronization & Storage

| Control | Local Folders | POP | IMAP | Exchange (EWS) |
|---|---|---|---|---|
| Save copies of all folders and messages on this computer for offline use | No | No | Yes | Yes |
| Offline folder settings… | No | No | Yes | Yes |
| Download limits (section) | No | No | Yes | Yes |
| Synchronize all messages locally regardless of age, or only the most recent … | No | No | Yes | Yes |
| Skip downloading messages larger than … KB | No | Yes | Yes | Yes |
| Deletion settings (delete old messages) | Yes | Yes | Yes | Yes |

The deletion section is on all four, but its explanation differs, and the difference matters:

- Local Folders: "To recover disk space, old messages can be permanently deleted."
- POP: "To recover disk space, old messages can be permanently deleted, including originals on
  the remote server."
- IMAP and Exchange: "Set rules to automatically delete old emails from both this computer and
  the mail server to free up space."

So for POP, IMAP and Exchange, these rules can delete messages on the server too. For Local
Folders they only delete local messages.

## What this means for articles

- If an article says "Synchronization & Storage", say that POP and Local Folders call the
  page Disk Space, or limit the article to IMAP and Exchange.
- Instructions about "Leave messages on server" or "Fetch headers only" are POP only.
- The "Deleting messages" options are for IMAP and Exchange only. Exchange has no "Mark as
  deleted without moving".
- Instant notification of new messages from the server is IMAP only.
- Local Folders has no Server Settings page, no Return Receipts page and no End-To-End
  Encryption page.

## Not covered

News (NNTP), feed (RSS) and chat accounts have their own variations. This document does not
cover them. The code also has a Microsoft Graph account type. It is treated like Exchange in
the places above, but this document does not cover it.

## Sources

All in the `omni.ja` of Thunderbird 160.0 beta. The `hidefor` attribute on an element lists the
account types that do not see it.

- `chrome/messenger/content/messenger/AccountManager.js`: which pages each account gets, and
  the choice between Disk Space and Synchronization & Storage.
- `modules/MDNService.sys.mjs` and `modules/AME2E.sys.mjs`: Return Receipts and End-To-End
  Encryption are hidden for Local Folders (`none`), news, feeds and chat.
- `chrome/messenger/content/messenger/am-serverwithnoidentities.xhtml`: the Local Folders page.
- `chrome/messenger/content/messenger/am-server.xhtml` and `am-server-advanced.js`: Server
  Settings and the Advanced… dialog.
- `chrome/messenger/content/messenger/am-offline.xhtml`: Disk Space and Synchronization &
  Storage.
- The texts come from `tools/ui-strings/strings/160.0.tsv`.
