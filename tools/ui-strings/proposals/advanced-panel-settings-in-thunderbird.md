# Proposed edit: advanced-panel-settings-in-thunderbird

Article: https://support.mozilla.org/en-US/kb/advanced-panel-settings-in-thunderbird
Edit: https://support.mozilla.org/en-US/kb/advanced-panel-settings-in-thunderbird/edit

Made by `tools/ui-strings/propose_edits.py` (thunderbird/sumo-linter#28) from the corpus snapshot of 2026-10-31. Paste `advanced-panel-settings-in-thunderbird.wiki` into the edit page, search it for `CHECK` and resolve every comment, check the screenshots, preview with the version selector set to 159 and to 153, then submit.

- 27 lines wrapped in `{for not tb159}…{/for}{for tb159}…{/for}`.
- 8 texts replaced automatically (one-for-one changes).
- 6 texts replaced by a strong guess (at least 75% similar), each line marked `<!-- CHECK the 159 string is correct -->`.
- 19 texts with a `CHECK 159` comment: the new text is a guess, decide by hand.
- 4 heading matches and 0 matches not found as written, each with a `CHECK 159` comment.
- sumo-lint errors: 0 before, 0 after.

| Line | What | Old text | New text, or closest new text |
|---|---|---|---|
| 18 | CHECK comment | When sending messages, always request a return receipt | Always request a return receipt when sending emails (new ID `return-receipt-request-control.label` in `receipts.ftl`, was `return-receipt-checkbox-control.label`; sheet record 240 planned “Always request a return receipt when sending emails”) |
| 20 | guessed: check | Leave it in my Inbox | Leave in Inbox (new ID `receipt-leave-inbox-control.label` in `receipts.ftl`, was `receipt-leave-radio-control.label`; sheet record 53 planned “Leave it in Inbox”) |
| 21 | guessed: check | Move it to my “Sent” folder | Move to Sent folder (new ID `receipt-move-sent-control.label` in `receipts.ftl`, was `receipt-move-radio-control.label`; sheet record 240 planned “Move to Sent folder”) |
| 22 | guessed: check | When I receive a request for a return receipt: | When a sender requests a return receipt: (new ID `receipt-sender-request-label` in `receipts.ftl`, was `receipt-request-label`; sheet record 240 planned “When a sender requests a return receipt:”) |
| 27 | replaced | Use autoscrolling | Enable auto-scrolling (new ID `enable-autoscroll-label.label` in `preferences.ftl`, was `autoscroll-label.label`; sheet record 13 planned “Enable auto-scrolling”) |
| 31 | heading: CHECK comment | System Integration | System settings (new ID `system-settings-legend` in `preferences.ftl`, was `system-integration-legend`; sheet record 7 planned “System settings”) |
| 32 | CHECK comment | Always check to see if Thunderbird is the default mail client on startup | System settings |
| 41 | CHECK comment | Enable Global Search and Indexer | Search & performance |
| 42 | guessed: check | Message Store Type for new accounts: | Storage format for new accounts: (new ID `storage-format-label.value` in `preferences.ftl`, was `store-type-label.value`; sheet record 77 planned “Storage format for new accounts:”) |
| 43 | CHECK comment | Use hardware acceleration when available | Use graphics acceleration for smoother scrolling and performance (new ID `allow-graphics-accel.label` in `preferences.ftl`, was `allow-hw-accel.label`; sheet record 77 planned “Use graphics acceleration for smoother scrolling and performance”) |
| 44 | replaced | Config Editor… | Advanced settings (new ID `advanced-settings-button.label` in `preferences.ftl`, was `config-editor-button.label`; sheet record 75 planned “Advanced settings”) |
| 56 | heading: CHECK comment | Network & Disk Space | Network and storage (new ID `general-network-and-storage-header` in `preferences.ftl`, was `general-network-and-diskspace-header`; sheet record 65 planned “Network and storage”) |
| 56 | heading: CHECK comment | Disk Space | Temporary storage (new ID `temporary-storage-legend` in `preferences.ftl`, was `diskspace-legend`; sheet record 67 planned “Temporary storage”) |
| 70 | CHECK comment | Auto-detect proxy settings for this network | Automatically detect network proxy (new ID `proxy-autodetect-network.label` in `connection.ftl`, was `proxy-type-wpad.label`; sheet record 65 planned “Use system proxy settings”) |
| 72 | CHECK comment | Manual proxy configuration: | Manual proxy setup: (new ID `proxy-manual-setup.label` in `connection.ftl`, was `proxy-type-manual.label`; sheet record 65 planned “Manual proxy setup:”) |
| 74 | CHECK comment | No proxy for: | Manual proxy setup: |
| 75 | CHECK comment | Automatic proxy configuration URL: | Automatic setup script URL: (new ID `proxy-auto-script-url.label` in `connection.ftl`, was `proxy-type-auto.label`; sheet record 65 planned “Automatic setup script URL:”) |
| 86 | CHECK comment | Automatically follow detected online state | Automatically switch modes when an internet connection is found (new ID `autodetect-connection-label.label` in `offline.ftl`, was `autodetect-online-label.label`; sheet record 64 planned “Automatically switch modes when an internet connection is found”) |
| 87 | CHECK comment | Automatically follow detected online state | Automatically switch modes when an internet connection is found (new ID `autodetect-connection-label.label` in `offline.ftl`, was `autodetect-online-label.label`; sheet record 64 planned “Automatically switch modes when an internet connection is found”) |
| 87 | CHECK comment | Manual state when starting up: | Automatically switch modes when an internet connection is found |
| 87 | CHECK comment | Remember previous online state | Ask whether to connect online (new ID `status-radio-ask-connect.label` in `offline.ftl`, was `status-radio-remember.label`; sheet record 64 planned “Ask whether to connect online”) |
| 87 | CHECK comment | Ask me for online state | Ask before downloading (new ID `going-offline-ask-download.label` in `offline.ftl`, was `status-radio-ask.label`; sheet record 64 planned “Ask before downloading”) |
| 91 | heading: CHECK comment | Disk Space | Temporary storage (new ID `temporary-storage-legend` in `preferences.ftl`, was `diskspace-legend`; sheet record 67 planned “Temporary storage”) |
| 92 | CHECK comment | Disk Space | Temporary storage (new ID `temporary-storage-legend` in `preferences.ftl`, was `diskspace-legend`; sheet record 67 planned “Temporary storage”) |
| 93 | CHECK comment | Disk Space | Temporary storage (new ID `temporary-storage-legend` in `preferences.ftl`, was `diskspace-legend`; sheet record 67 planned “Temporary storage”) |
| 93 | CHECK comment | Clear Now | Clear temporary files (new ID `clear-temp-files-button.label` in `preferences.ftl`, was `clear-cache-button.label`; sheet record 67 planned “Clear temporary files”) |
| 95 | replaced | Compact all folders when it will save over | Remove data from folders when they have already been deleted to free up storage (new ID `offline-compact-remove-deleted.label` in `preferences.ftl`, was `offline-compact-folder.label`) |
| 95 | CHECK comment | Disk Space | Temporary storage (new ID `temporary-storage-legend` in `preferences.ftl`, was `diskspace-legend`; sheet record 67 planned “Temporary storage”) |
| 104 | guessed: check | Automatically install updates (recommended: improved security) | Automatically install updates (recommended) (new ID `install-updates-automatically-label.label` in `preferences.ftl`, was `automatic-updates-label.label`; sheet record 61 planned “Automatically install updates (Recommended)”) |
| 106 | replaced | Check for updates, but let me choose whether to install them | Check for updates, but ask before installing (new ID `check-updates-ask-label.label` in `preferences.ftl`, was `check-updates-label.label`) |
| 108 | replaced | Show Update History | Show history (new ID `show-history-button.label` in `preferences.ftl`, was `update-history-button.label`; sheet record 59 planned “Show history”) |
| 116 | guessed: check | Automatically install updates (recommended: improved security) | Automatically install updates (recommended) (new ID `install-updates-automatically-label.label` in `preferences.ftl`, was `automatic-updates-label.label`; sheet record 61 planned “Automatically install updates (Recommended)”) |
| 118 | replaced | Check for updates, but let me choose whether to install them | Check for updates, but ask before installing (new ID `check-updates-ask-label.label` in `preferences.ftl`, was `check-updates-label.label`) |
| 120 | replaced | Show Update History | Show history (new ID `show-history-button.label` in `preferences.ftl`, was `update-history-button.label`; sheet record 59 planned “Show history”) |
| 131 | CHECK comment | When a server requests my personal certificate: | When a server asks for a certificate to verify your identity: (new ID `certificate-verify-description` in `preferences.ftl`, was `certificate-description`) |
| 131 | CHECK comment | Select one automatically | Choose a certificate automatically (new ID `certificate-choose-auto.label` in `preferences.ftl`, was `certificate-auto.label`; sheet record 148 planned “Choose a certificate automatically”) |
| 133 | replaced | Query OCSP responder servers to confirm the current validity of certificates | Check certificate validation servers (OCSP) to confirm certificates are still correct. (new ID `ocsp-check-label.label` in `preferences.ftl`, was `ocsp-label.label`) |
