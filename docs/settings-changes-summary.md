# Settings and Account Settings changes: short summaries

Two summaries of the en-US Settings and Account Settings string changes, each under 350
characters, for messages to people such as SUMO localizers (sumo-linter #25). They describe ESR
153.6.0, Release 159.0 and Beta 160.0, compared on 2026-10-31.

## ESR 153 to 159

> Thunderbird 159 rewords most of Settings, largely into sentence case: General (Start Page,
> system integration, auto-scrolling, language and fonts, notifications, proxy, temporary
> storage), Composition, and Privacy & Security. In Account Settings, only spam settings,
> OAuth2 options under Server Settings > Advanced…, and OpenPGP key dialogs change.

## 159 to 160

> Thunderbird 160 rewords the main Account Settings pages: Server Settings (security and
> sign-in, checking and deleting messages), Copies & Folders, Composition & Addressing,
> Synchronization & Storage, and End-To-End Encryption. Settings has almost no visible change:
> most of its changed strings moved to a new file format with the same text.

## Basis

The counts come from the 3-column localizer tables in `tools/ui-strings/`:

| Table | Changed in 159 | Changed in 160 | Changed in both |
|---|---|---|---|
| Settings | 170 rows | 33 rows | 1 row |
| Account Settings | 45 rows | 34 rows | 0 rows |

Read these counts with two limits:

- Most of the 33 Settings rows marked 160 are not visible changes. Thunderbird moved those
  strings from `.properties` files to Fluent, and only the placeholder syntax or the apostrophe
  style changed. sumo-linter #24 proposes to leave such rows out.
- Many of the 45 Account Settings rows marked 159 are strings that 159 removed, for example
  "Notify on new Mail" or "Proxy Settings:". Nobody checked whether 153 still showed them, so
  some can be old strings that no page used.

The details are in `tools/ui-strings/strings-153.6.0-159.0-160.0-settings.md` and
`tools/ui-strings/strings-153.6.0-159.0-160.0-account-settings.md`.
