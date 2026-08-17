/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! `sumo-lint-lsp` — Language Server Protocol server for SUMO wiki markup.
//!
//! One server, every editor: VS Code and Neovim both speak LSP, so this replaces
//! what would otherwise be two plugins. Neovim needs no plugin code at all, just
//! `vim.lsp.start`.
//!
//! Implemented by hand over stdio rather than with `tower-lsp`, because the
//! surface needed is small — `initialize`, document sync, `publishDiagnostics`,
//! `formatting` and `codeAction` — and keeping the workspace dependency-free
//! means a Rust toolchain is the only build requirement.
//!
//! LSP positions are UTF-16 code units, while our spans are byte offsets. That
//! conversion is done in [`to_position`] and is not optional: getting it wrong
//! misplaces squiggles in any article containing non-ASCII text, and the corpus
//! has Arabic, Japanese, and em-dashes.

use std::collections::HashMap;
use std::io::{self, BufRead, Write};
use std::ops::Range;

use sumo_wiki_core::{Applicability, Diagnostic, Document, Severity, Style};

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let mut docs: HashMap<String, String> = HashMap::new();

    loop {
        let Some(body) = read_message(&mut reader)? else {
            return Ok(());
        };
        let method = field_str(&body, "method").unwrap_or_default();
        let id = field_raw(&body, "id");

        match method.as_str() {
            "initialize" => {
                // textDocumentSync 1 = full text on every change. Articles are
                // tens of kilobytes, so re-lexing whole documents is cheap and
                // avoids incremental-sync bookkeeping bugs.
                respond(
                    id.as_deref(),
                    r#"{"capabilities":{"textDocumentSync":1,"documentFormattingProvider":true,"codeActionProvider":{"codeActionKinds":["quickfix","source.fixAll.sumo-lint"]}},"serverInfo":{"name":"sumo-lint-lsp","version":"0.1.0"}}"#,
                )?;
            }
            // Format on save / "Format Document". This is how phase-2 house style
            // reaches editors, and why the LSP was built before phase 2.
            "textDocument/formatting" => {
                let result = match field_str(&body, "uri").and_then(|u| docs.get(&u).cloned()) {
                    Some(text) => {
                        let formatted = Document::parse(text.clone()).format(&Style::thunderbird());
                        if formatted == text {
                            // No edits at all: the churn-avoiding default means a
                            // conforming article is returned untouched.
                            "[]".to_string()
                        } else {
                            format!("[{}]", whole_document_edit(&text, &formatted))
                        }
                    }
                    None => "[]".to_string(),
                };
                respond(id.as_deref(), &result)?;
            }
            // Quick fixes. Without this a squiggle is a dead end: the editor
            // falls through to whatever other provider is installed, and for
            // SW009 an AI assistant will happily "fix" wiki markup into the
            // Markdown link syntax the rule exists to flag.
            "textDocument/codeAction" => {
                let result = match field_str(&body, "uri") {
                    Some(uri) => match docs.get(&uri) {
                        Some(text) => code_actions(&uri, text, &body),
                        None => "[]".to_string(),
                    },
                    None => "[]".to_string(),
                };
                respond(id.as_deref(), &result)?;
            }
            "shutdown" => respond(id.as_deref(), "null")?,
            "exit" => return Ok(()),
            "textDocument/didOpen" | "textDocument/didChange" => {
                if let Some(uri) = field_str(&body, "uri") {
                    let text = extract_text(&body).unwrap_or_default();
                    docs.insert(uri.clone(), text.clone());
                    publish(&uri, &text)?;
                }
            }
            "textDocument/didClose" => {
                if let Some(uri) = field_str(&body, "uri") {
                    docs.remove(&uri);
                    // Clear stale squiggles, or they linger after closing.
                    notify(&format!(
                        r#"{{"method":"textDocument/publishDiagnostics","params":{{"uri":{},"diagnostics":[]}}}}"#,
                        json_str(&uri)
                    ))?;
                }
            }
            _ => {
                // Unknown request: reply so the client is not left waiting.
                if id.is_some() {
                    respond(id.as_deref(), "null")?;
                }
            }
        }
    }
}

/// Lint `text` and publish diagnostics for `uri`.
fn publish(uri: &str, text: &str) -> io::Result<()> {
    let doc = Document::parse(text);
    let items: Vec<String> = doc
        .diagnostics()
        .iter()
        .map(|d| diagnostic_json(text, d))
        .collect();

    notify(&format!(
        r#"{{"method":"textDocument/publishDiagnostics","params":{{"uri":{},"diagnostics":[{}]}}}}"#,
        json_str(uri),
        items.join(",")
    ))
}

/// One `Diagnostic` as LSP JSON.
///
/// Shared with the code-action handler so the `diagnostics` it attaches to each
/// quick fix are byte-identical to the published ones — that is how the client
/// pairs a fix with its squiggle, and the "(fixable)" suffix is part of the
/// message it matches on.
fn diagnostic_json(text: &str, d: &Diagnostic) -> String {
    let hint = match d.fix.as_ref().map(|f| f.applicability) {
        Some(Applicability::Safe) => " (fixable)",
        Some(Applicability::Unsafe) => " (fix available, needs review)",
        None => "",
    };
    format!(
        r#"{{"range":{},"severity":{},"code":"{}","source":"sumo-lint","message":{}}}"#,
        range_json(text, &d.span),
        match d.severity {
            Severity::Error => 1,
            Severity::Warning => 2,
        },
        d.code,
        json_str(&format!("{}{hint}", d.message))
    )
}

/// Quick fixes for the fixable diagnostics overlapping the requested range,
/// plus a document-wide `source.fixAll.sumo-lint` action.
///
/// `Unsafe` fixes are offered too, unlike in `--fix`: a code action is an
/// explicit, reviewable, undoable choice by the author, so the CLI's
/// don't-touch-it default would only push people toward guessing by hand. The
/// title says so.
fn code_actions(uri: &str, text: &str, body: &str) -> String {
    let (start, end) = match parse_range(body) {
        Some((s, e)) => (from_position(text, s), from_position(text, e)),
        // Unparsable range: treat the request as covering the whole document
        // rather than silently offering nothing.
        None => (0, text.len()),
    };

    let doc = Document::parse(text);
    let diagnostics = doc.diagnostics();
    let mut actions: Vec<String> = Vec::new();

    for d in &diagnostics {
        let Some(fix) = d.fix.as_ref() else { continue };
        // Overlap, not containment: the client sends a zero-width range at the
        // caret, which no span contains.
        if fix.span.start > end || fix.span.end < start {
            continue;
        }
        let safe = fix.applicability == Applicability::Safe;
        let title = format!(
            "{}: {}{}",
            d.code,
            fix.description,
            if safe { "" } else { " (needs review)" }
        );
        actions.push(format!(
            r#"{{"title":{},"kind":"quickfix","isPreferred":{},"diagnostics":[{}],"edit":{{"changes":{{{}:[{{"range":{},"newText":{}}}]}}}}}}"#,
            json_str(&title),
            safe,
            diagnostic_json(text, d),
            json_str(uri),
            range_json(text, &fix.span),
            json_str(&fix.replacement)
        ));
    }

    // Offered whenever anything is safely fixable, even for a single fix, so
    // `editor.codeActionsOnSave` has something to call.
    let (fixed, count) = doc.apply_fixes(false);
    if count > 0 && fixed != text {
        let plural = if count == 1 { "fix" } else { "fixes" };
        actions.push(format!(
            r#"{{"title":{},"kind":"source.fixAll.sumo-lint","edit":{{"changes":{{{}:[{}]}}}}}}"#,
            json_str(&format!("sumo-lint: apply {count} safe {plural}")),
            json_str(uri),
            whole_document_edit(text, &fixed)
        ));
    }

    format!("[{}]", actions.join(","))
}

/// A `TextEdit` replacing the whole document.
fn whole_document_edit(text: &str, new_text: &str) -> String {
    let end = to_position(text, text.len());
    format!(
        r#"{{"range":{{"start":{{"line":0,"character":0}},"end":{{"line":{},"character":{}}}}},"newText":{}}}"#,
        end.0,
        end.1,
        json_str(new_text)
    )
}

/// A byte span as an LSP `Range`.
fn range_json(text: &str, span: &Range<usize>) -> String {
    let (s, e) = (to_position(text, span.start), to_position(text, span.end));
    format!(
        r#"{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}}"#,
        s.0, s.1, e.0, e.1
    )
}

/// Byte offset to a zero-based LSP position, counted in UTF-16 code units.
fn to_position(text: &str, offset: usize) -> (usize, usize) {
    let upto = &text[..offset.min(text.len())];
    let line = upto.bytes().filter(|c| *c == b'\n').count();
    let last = upto.rsplit('\n').next().unwrap_or("");
    (line, last.chars().map(char::len_utf16).sum())
}

/// Inverse of [`to_position`]: a UTF-16 position back to a byte offset.
///
/// A position past the end of a line or of the document clamps, because clients
/// do send `character` values beyond the last column.
fn from_position(text: &str, (line, character): (usize, usize)) -> usize {
    let mut offset = 0usize;
    for (n, l) in text.split_inclusive('\n').enumerate() {
        if n == line {
            let mut units = 0usize;
            // The newline is not an addressable column, so a `character` past
            // the last one clamps to the line end instead of the next line.
            for c in l.trim_end_matches('\n').chars() {
                if units >= character {
                    break;
                }
                units += c.len_utf16();
                offset += c.len_utf8();
            }
            return offset;
        }
        offset += l.len();
    }
    text.len()
}

/// Read `params.range` as `((line, character), (line, character))`.
///
/// The first `"range"` in a codeAction request is `params.range`; the ones in
/// `context.diagnostics` follow it. A client that ordered those fields the other
/// way round would give us a diagnostic's range instead — still inside the
/// region of interest, so the degradation is graceful rather than wrong.
fn parse_range(body: &str) -> Option<((usize, usize), (usize, usize))> {
    let rest = &body[body.find("\"range\"")?..];
    let (l1, at) = next_uint(rest, "\"line\"", 0)?;
    let (c1, at) = next_uint(rest, "\"character\"", at)?;
    let (l2, at) = next_uint(rest, "\"line\"", at)?;
    let (c2, _) = next_uint(rest, "\"character\"", at)?;
    Some(((l1, c1), (l2, c2)))
}

/// Find `key` at or after `from` and parse the integer after its colon,
/// returning the value and where to resume scanning.
fn next_uint(s: &str, key: &str, from: usize) -> Option<(usize, usize)> {
    let p = s.get(from..)?.find(key)? + from;
    let after = p + key.len();
    let r = s[after..].trim_start().strip_prefix(':')?.trim_start();
    let digits: String = r.chars().take_while(|c| c.is_ascii_digit()).collect();
    Some((digits.parse().ok()?, after))
}

// ---------------------------------------------------------------------------
// Minimal LSP framing and JSON handling
// ---------------------------------------------------------------------------

/// Read one `Content-Length`-framed message body.
fn read_message(reader: &mut impl BufRead) -> io::Result<Option<String>> {
    let mut len = 0usize;
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line)? == 0 {
            return Ok(None);
        }
        let t = line.trim_end();
        if t.is_empty() {
            break;
        }
        if let Some(v) = t.strip_prefix("Content-Length:") {
            len = v.trim().parse().unwrap_or(0);
        }
    }
    if len == 0 {
        return Ok(Some(String::new()));
    }
    let mut buf = vec![0u8; len];
    reader.read_exact(&mut buf)?;
    Ok(Some(String::from_utf8_lossy(&buf).into_owned()))
}

fn send(payload: &str) -> io::Result<()> {
    let out = io::stdout();
    let mut lock = out.lock();
    write!(lock, "Content-Length: {}\r\n\r\n{}", payload.len(), payload)?;
    lock.flush()
}

fn respond(id: Option<&str>, result: &str) -> io::Result<()> {
    let id = id.unwrap_or("null");
    send(&format!(
        r#"{{"jsonrpc":"2.0","id":{id},"result":{result}}}"#
    ))
}

/// Send a notification, splicing `inner`'s fields in after `"jsonrpc"`.
///
/// Uses `strip_prefix`/`strip_suffix`, which remove at most one brace.
/// `trim_end_matches('}')` looks equivalent but strips *every* trailing brace,
/// which truncated the diagnostics payload into invalid JSON.
fn notify(inner: &str) -> io::Result<()> {
    let body = inner.strip_prefix('{').unwrap_or(inner);
    let body = body.strip_suffix('}').unwrap_or(body);
    send(&format!(r#"{{"jsonrpc":"2.0",{body}}}"#))
}

/// Extract a string field's value. Sufficient for the handful of fields this
/// server reads; not a general JSON parser.
fn field_str(body: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\"");
    let mut from = 0usize;
    while let Some(p) = body[from..].find(&pat).map(|x| x + from) {
        let after = &body[p + pat.len()..];
        let rest = after.trim_start();
        if let Some(r) = rest.strip_prefix(':') {
            let r = r.trim_start();
            if let Some(q) = r.strip_prefix('"') {
                return Some(unescape(q.split('"').next().unwrap_or("")));
            }
        }
        from = p + pat.len();
    }
    None
}

/// Extract a raw (unquoted) field value, e.g. a numeric request id.
fn field_raw(body: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\"");
    let p = body.find(&pat)?;
    let r = body[p + pat.len()..]
        .trim_start()
        .strip_prefix(':')?
        .trim_start();
    let end = r.find([',', '}']).unwrap_or(r.len());
    let v = r[..end].trim();
    (!v.is_empty()).then(|| v.to_string())
}

/// Pull `text` out of a didOpen/didChange payload.
///
/// `text` is the last string field in both shapes, and its value may contain
/// escaped quotes, so it is scanned with escape awareness rather than split on
/// the next `"`.
fn extract_text(body: &str) -> Option<String> {
    let p = body.rfind("\"text\"")?;
    let r = body[p + 6..].trim_start().strip_prefix(':')?.trim_start();
    let r = r.strip_prefix('"')?;
    let mut out = String::new();
    let mut chars = r.chars();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Some(out),
            '\\' => match chars.next() {
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('t') => out.push('\t'),
                Some('"') => out.push('"'),
                Some('\\') => out.push('\\'),
                Some('u') => {
                    let hex: String = chars.by_ref().take(4).collect();
                    if let Some(c) = u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32) {
                        out.push(c);
                    }
                }
                Some(other) => out.push(other),
                None => break,
            },
            c => out.push(c),
        }
    }
    Some(out)
}

fn unescape(s: &str) -> String {
    s.replace("\\/", "/")
        .replace("\\\\", "\\")
        .replace("\\\"", "\"")
}

fn json_str(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    o.push('"');
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utf16_positions_account_for_wide_characters() {
        // "日本語" is 9 bytes but 3 UTF-16 units; an emoji outside the BMP is 2.
        let text = "日本語x\n";
        assert_eq!(to_position(text, 0), (0, 0));
        assert_eq!(to_position(text, 9), (0, 3));
        assert_eq!(to_position(text, 10), (0, 4));
        let text = "😀x";
        assert_eq!(
            to_position(text, 4),
            (0, 2),
            "astral char is 2 UTF-16 units"
        );
    }

    #[test]
    fn extracts_text_with_escapes() {
        let body = r#"{"params":{"textDocument":{"uri":"file:///a.wiki","text":"a\nb\"c\\d"}}}"#;
        assert_eq!(extract_text(body).unwrap(), "a\nb\"c\\d");
        assert_eq!(field_str(body, "uri").unwrap(), "file:///a.wiki");
    }

    #[test]
    fn positions_round_trip_through_bytes() {
        let text = "日本語x\nsecond line\n";
        for offset in (0..=text.len()).filter(|o| text.is_char_boundary(*o)) {
            assert_eq!(
                from_position(text, to_position(text, offset)),
                offset,
                "offset {offset}"
            );
        }
        // Clamping, which clients rely on. Past the last column stops at the end
        // of that line, never wrapping onto the newline.
        assert_eq!(from_position(text, (0, 99)), 10, "past end of line 1");
        assert_eq!(from_position(text, (9, 0)), text.len(), "past end of text");
    }

    #[test]
    fn parses_the_params_range_not_a_diagnostic_range() {
        let body = r#"{"id":3,"method":"textDocument/codeAction","params":{"textDocument":{"uri":"file:///a.wiki"},"range":{"start":{"line":2,"character":4},"end":{"line":2,"character":9}},"context":{"diagnostics":[{"range":{"start":{"line":7,"character":0},"end":{"line":7,"character":1}}}]}}}"#;
        assert_eq!(parse_range(body).unwrap(), ((2, 4), (2, 9)));
    }

    /// The whole point of the feature: Cmd+. on a Markdown link must produce
    /// SUMO's `[url label]`, not leave the field to another provider that
    /// "fixes" it back into Markdown.
    #[test]
    fn quick_fix_rewrites_a_markdown_link_as_wiki_syntax() {
        let text = "See [linktext](https://someurl.com) here.\n";
        let body = r#"{"params":{"textDocument":{"uri":"file:///a.wiki"},"range":{"start":{"line":0,"character":6},"end":{"line":0,"character":6}},"context":{"diagnostics":[]}}}"#;
        let actions = code_actions("file:///a.wiki", text, body);
        assert!(
            actions.contains(r#""newText":"[https://someurl.com linktext]""#),
            "quick fix should insert wiki link syntax, got: {actions}"
        );
        assert!(actions.contains(r#""title":"SW009: rewrite as wiki link syntax""#));
        assert!(
            actions.contains(r#""isPreferred":true"#),
            "a safe fix is the preferred/auto fix"
        );
        // The span covers `[linktext](https://someurl.com)`, columns 4..35.
        assert!(actions.contains(
            r#""range":{"start":{"line":0,"character":4},"end":{"line":0,"character":35}}"#
        ));
        // And the document-wide action, for codeActionsOnSave.
        assert!(actions.contains(r#""kind":"source.fixAll.sumo-lint""#));
        assert!(actions.contains(r#""title":"sumo-lint: apply 1 safe fix""#));
    }

    #[test]
    fn quick_fixes_are_limited_to_the_requested_range() {
        // Two fixable errors, one per line. The bold needs text before it: a
        // line-leading `**` is a nested list marker in wiki markup, not bold.
        let text = "[a](http://x)\nsee **bold** here\n";
        // A whole-line selection, as sent when the user selects the line. A
        // collapsed caret only turns up the fix it actually sits inside, which is
        // how every other language server behaves.
        let range = |line| {
            format!(
                r#"{{"params":{{"range":{{"start":{{"line":{line},"character":0}},"end":{{"line":{line},"character":99}}}}}}}}"#
            )
        };
        let first = code_actions("file:///a.wiki", text, &range(0));
        assert!(first.contains("SW009"), "got: {first}");
        assert!(
            !first.contains("SW010"),
            "line 1's fix must not be offered on line 0: {first}"
        );
        let second = code_actions("file:///a.wiki", text, &range(1));
        assert!(second.contains("SW010"), "got: {second}");
        assert!(
            !second.contains("SW009"),
            "line 0's fix must not be offered on line 1: {second}"
        );
    }

    #[test]
    fn no_diagnostics_means_no_actions() {
        let clean = "See [https://someurl.com linktext] here.\n";
        let body = r#"{"params":{"range":{"start":{"line":0,"character":0},"end":{"line":0,"character":0}}}}"#;
        assert_eq!(code_actions("file:///a.wiki", clean, body), "[]");
    }

    #[test]
    fn reads_framed_messages() {
        let payload = r#"{"jsonrpc":"2.0","id":1,"method":"initialize"}"#;
        let raw = format!("Content-Length: {}\r\n\r\n{}", payload.len(), payload);
        let mut cur = io::Cursor::new(raw.into_bytes());
        let got = read_message(&mut cur).unwrap().unwrap();
        assert_eq!(got, payload);
        assert_eq!(field_str(&got, "method").unwrap(), "initialize");
        assert_eq!(field_raw(&got, "id").unwrap(), "1");
    }
}
