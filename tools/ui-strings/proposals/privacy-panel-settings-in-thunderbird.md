# Proposed edit: privacy-panel-settings-in-thunderbird

Article: https://support.mozilla.org/en-US/kb/privacy-panel-settings-in-thunderbird
Edit: https://support.mozilla.org/en-US/kb/privacy-panel-settings-in-thunderbird/edit

Made by `tools/ui-strings/propose_edits.py` (thunderbird/sumo-linter#28) from the corpus snapshot of 2026-10-31. Paste `privacy-panel-settings-in-thunderbird.wiki` into the edit page, search it for `CHECK` and resolve every comment, check the screenshots, preview with the version selector set to 159 and to 153, then submit.

- 11 lines wrapped in `{for not tb159}…{/for}{for tb159}…{/for}`.
- 2 texts replaced automatically (one-for-one changes).
- 5 texts replaced by a strong guess (at least 75% similar), each line marked `<!-- CHECK the 159 string is correct -->`.
- 7 texts with a `CHECK 159` comment: the new text is a guess, decide by hand.
- 2 heading matches and 0 matches not found as written, each with a `CHECK 159` comment.
- sumo-lint errors: 0 before, 0 after.

| Line | What | Old text | New text, or closest new text |
|---|---|---|---|
| 7 | heading: CHECK comment | Mail Content | Email content (new ID `email-content` in `preferences.ftl`, was `mail-content`) |
| 8 | guessed: check | Allow remote content in messages | Allow remote content (images and styles) (new ID `remote-content-images-label.label` in `preferences.ftl`, was `remote-content-label.label`; sheet record 123 planned “Allow remote content (images and styles)”) |
| 15 | replaced | From visited | From visited sites only (new ID `third-party-visited-only.label` in `preferences.ftl`, was `third-party-visited.label`) |
| 20 | guessed: check | Ask me every time | Ask every time (new ID `certificate-ask-every.label` in `preferences.ftl`, was `certificate-ask.label`; sheet record 148 planned “Ask every time”) |
| 24 | guessed: check | Saved Passwords… | View Saved Passwords… (new ID `view-saved-passwords-button.label` in `preferences.ftl`, was `passwords-button.label`; sheet record 132 planned “View Saved Passwords…”) |
| 25 | guessed: check | Use a Primary Password | Use Primary Password (new ID `use-primary-password-label.label` in `preferences.ftl`, was `primary-password-label.label`; sheet record 133 planned “Use Primary Password”) |
| 33 | heading: CHECK comment | Thunderbird Data Collection and Use | Thunderbird is built by a global community. Sharing anonymous performance data helps us fix bugs faster and make the app faster for everyone. |
| 34 | CHECK comment | Allow Thunderbird to | Keeps Thunderbird secure with the latest security fixes. |
| 35 | CHECK comment | Allow Thunderbird to send backlogged crash reports on your behalf | Send anonymous crash reports to { -vendor-short-name } (new ID `collection-share-crash-data.label` in `preferences.ftl`, was `collection-backlogged-crash-reports.label`) |
| 35 | CHECK comment | Allow Thunderbird to | Keeps Thunderbird secure with the latest security fixes. |
| 39 | CHECK comment | Tell me if the message I’m reading is a suspected email scam | Thunderbird checks messages for phishing links and common signs of email scams. (new ID `scam-detection-description` in `preferences.ftl`, was `phishing-label.label`) |
| 42 | CHECK comment | Allow antivirus clients to quarantine individual incoming messages | Allow antivirus software to isolate infected incoming emails (new ID `antivirus-isolate-label.label` in `preferences.ftl`, was `antivirus-label.label`; sheet record 144 planned “Allow antivirus software to isolate infected incoming emails”) |
| 46 | CHECK comment | When a server requests my personal certificate: | When a server asks for a certificate to verify your identity: (new ID `certificate-verify-description` in `preferences.ftl`, was `certificate-description`) |
| 46 | CHECK comment | Select one automatically | Choose a certificate automatically (new ID `certificate-choose-auto.label` in `preferences.ftl`, was `certificate-auto.label`; sheet record 148 planned “Choose a certificate automatically”) |
| 46 | guessed: check | Ask me every time | Ask every time (new ID `certificate-ask-every.label` in `preferences.ftl`, was `certificate-ask.label`; sheet record 148 planned “Ask every time”) |
| 47 | replaced | Query OCSP responder servers to confirm the current validity of certificates | Check certificate validation servers (OCSP) to confirm certificates are still correct. (new ID `ocsp-check-label.label` in `preferences.ftl`, was `ocsp-label.label`) |
