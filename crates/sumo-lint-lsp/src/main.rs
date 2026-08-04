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
//! surface needed is small — `initialize`, document sync, `publishDiagnostics` —
//! and keeping the workspace dependency-free means a Rust toolchain is the only
//! build requirement.
//!
//! LSP positions are UTF-16 code units, while our spans are byte offsets. That
//! conversion is done in [`to_position`] and is not optional: getting it wrong
//! misplaces squiggles in any article containing non-ASCII text, and the corpus
//! has Arabic, Japanese, and em-dashes.

use std::collections::HashMap;
use std::io::{self, BufRead, Write};

use sumo_wiki_core::{Applicability, Document, Severity, Style};

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
                    r#"{"capabilities":{"textDocumentSync":1,"documentFormattingProvider":true},"serverInfo":{"name":"sumo-lint-lsp","version":"0.1.0"}}"#,
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
                            let end = to_position(&text, text.len());
                            format!(
                                r#"[{{"range":{{"start":{{"line":0,"character":0}},"end":{{"line":{},"character":{}}}}},"newText":{}}}]"#,
                                end.0,
                                end.1,
                                json_str(&formatted)
                            )
                        }
                    }
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
        .map(|d| {
            let (s, e) = (to_position(text, d.span.start), to_position(text, d.span.end));
            let hint = match d.fix.as_ref().map(|f| f.applicability) {
                Some(Applicability::Safe) => " (fixable)",
                Some(Applicability::Unsafe) => " (fix available, needs review)",
                None => "",
            };
            format!(
                r#"{{"range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}},"severity":{},"code":"{}","source":"sumo-lint","message":{}}}"#,
                s.0,
                s.1,
                e.0,
                e.1,
                match d.severity {
                    Severity::Error => 1,
                    Severity::Warning => 2,
                },
                d.code,
                json_str(&format!("{}{hint}", d.message))
            )
        })
        .collect();

    notify(&format!(
        r#"{{"method":"textDocument/publishDiagnostics","params":{{"uri":{},"diagnostics":[{}]}}}}"#,
        json_str(uri),
        items.join(",")
    ))
}

/// Byte offset to a zero-based LSP position, counted in UTF-16 code units.
fn to_position(text: &str, offset: usize) -> (usize, usize) {
    let upto = &text[..offset.min(text.len())];
    let line = upto.bytes().filter(|c| *c == b'\n').count();
    let last = upto.rsplit('\n').next().unwrap_or("");
    (line, last.chars().map(char::len_utf16).sum())
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
