/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Phase-1 rules: markup that is genuinely wrong, not merely unfashionable.
//!
//! Every rule here exists because the construct it guards is actually used in the
//! Thunderbird corpus (see `corpus/report.md`) or because the corpus contained a
//! real instance of the error. Rules for constructs nobody uses were not written.
//!
//! Deliberately **not** implemented, and why:
//!   - "Markdown heading `# Text`": `#` is SUMO's ordered-list marker, so `# Text`
//!     is valid wiki and indistinguishable from a Markdown heading. No such rule
//!     can exist. Likewise `*` is a list marker, not emphasis.
//!   - Heading spacing (`= H =` vs `=H=`): the corpus splits 53.9%/44.7% with no
//!     convention, so neither form may be called wrong. That is phase 2, and it
//!     awaits a community decision.

use crate::diagnostic::{Applicability, Diagnostic, Fix, Severity};
use crate::lexer::{LinkKind, MacroKind, Opaque, Token, TokenKind};

/// Image parameters accepted by Kitsune, from `kitsune/sumo/parser.py` (`IMAGE_PARAMS`).
pub const IMAGE_PARAMS: &[&str] = &[
    "alt", "align", "caption", "valign", "frame", "page", "link", "width", "height",
];

/// Every rule code this crate can emit, with a one-line description.
pub const RULES: &[(&str, &str)] = &[
    ("SW001", "unclosed or unopened {for} block"),
    ("SW002", "unclosed or unopened {note} block"),
    ("SW003", "unclosed or unopened {warning} block"),
    ("SW004", "unbalanced ''' bold markers in a paragraph"),
    (
        "SW005",
        "heading's opening and closing = runs differ in length",
    ),
    ("SW006", "unknown [[Image:]] parameter"),
    ("SW007", "unmatched [[ or ]]"),
    ("SW008", "empty list item"),
    ("SW009", "Markdown link syntax instead of wiki syntax"),
    ("SW010", "Markdown bold syntax instead of wiki syntax"),
    ("SW011", "empty macro argument"),
];

/// Run every rule over an already-lexed document.
pub fn check(input: &str, tokens: &[Token]) -> Vec<Diagnostic> {
    let mut out = Vec::new();
    blocks(input, tokens, &mut out);
    bold_balance(input, tokens, &mut out);
    headings(input, tokens, &mut out);
    image_params(input, tokens, &mut out);
    brackets(tokens, &mut out);
    empty_list_items(input, tokens, &mut out);
    markdown_syntax(input, tokens, &mut out);
    empty_macros(input, tokens, &mut out);
    out.sort_by_key(|d| (d.span.start, d.code));
    out
}

/// True for tokens whose contents are not interpreted as markup.
fn is_opaque(t: &Token) -> bool {
    matches!(t.kind, TokenKind::Opaque { .. })
}

// ---------------------------------------------------------------------------
// SW001 / SW002 / SW003 — block delimiter balance
// ---------------------------------------------------------------------------

/// Pair up `{for}`, `{note}` and `{warning}` with their closers.
///
/// Uses a stack rather than counting, so a stray closer is reported where it
/// actually appears instead of as a vague per-file imbalance. Tokens inside
/// `<code>`/`<nowiki>` never reach here — the lexer already sealed them into a
/// single opaque token — which is exactly the bug a regex-based audit hit.
fn blocks(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    let mut fors: Vec<&Token> = Vec::new();
    let mut notes: Vec<&Token> = Vec::new();
    let mut warns: Vec<&Token> = Vec::new();

    for t in tokens.iter().filter(|t| !is_opaque(t)) {
        match t.kind {
            TokenKind::ForOpen => fors.push(t),
            TokenKind::ForClose => {
                if fors.pop().is_none() {
                    out.push(Diagnostic::new(
                        "SW001",
                        Severity::Error,
                        "`{/for}` with no matching `{for}`",
                        t.span.clone(),
                    ));
                }
            }
            TokenKind::BlockOpen { warning } => {
                if warning {
                    warns.push(t)
                } else {
                    notes.push(t)
                }
            }
            TokenKind::BlockClose { warning } => {
                let (stack, code, name) = if warning {
                    (&mut warns, "SW003", "warning")
                } else {
                    (&mut notes, "SW002", "note")
                };
                if stack.pop().is_none() {
                    out.push(Diagnostic::new(
                        code,
                        Severity::Error,
                        format!("`{{/{name}}}` with no matching `{{{name}}}`"),
                        t.span.clone(),
                    ));
                }
            }
            _ => {}
        }
    }

    for (stack, code, name) in [
        (fors, "SW001", "for"),
        (notes, "SW002", "note"),
        (warns, "SW003", "warning"),
    ] {
        for t in stack {
            out.push(Diagnostic::new(
                code,
                Severity::Error,
                format!(
                    "`{}` is never closed; add `{{/{name}}}`",
                    t.text(input).trim()
                ),
                t.span.clone(),
            ));
        }
    }
}

// ---------------------------------------------------------------------------
// SW004 — bold balance
// ---------------------------------------------------------------------------

/// Report paragraphs containing an odd number of `'''`.
///
/// Counted per **paragraph**, not per line: bold-italic legitimately spans
/// several lines in real articles (`'''''intro … list items …'''''`), and a
/// per-line check reported both ends of a correctly balanced span as errors.
fn bold_balance(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    let mut para: Vec<&Token> = Vec::new();
    let mut blank_run = 0usize;

    let flush = |para: &mut Vec<&Token>, out: &mut Vec<Diagnostic>| {
        let bolds: Vec<&&Token> = para.iter().filter(|t| t.kind == TokenKind::Bold).collect();
        if bolds.len() % 2 == 1 {
            let last = bolds[bolds.len() - 1];
            out.push(Diagnostic::new(
                "SW004",
                Severity::Error,
                format!(
                    "unbalanced `'''`: {} bold markers in this paragraph, so one is unpaired",
                    bolds.len()
                ),
                last.span.clone(),
            ));
        }
        para.clear();
    };

    for t in tokens {
        match t.kind {
            TokenKind::Newline => {
                blank_run += 1;
                if blank_run >= 2 {
                    flush(&mut para, out);
                }
            }
            _ => {
                if !t.text(input).trim().is_empty() {
                    blank_run = 0;
                }
                if !is_opaque(t) {
                    para.push(t);
                }
            }
        }
    }
    flush(&mut para, out);
}

// ---------------------------------------------------------------------------
// SW005 — heading marker symmetry
// ---------------------------------------------------------------------------

fn headings(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    let mut i = 0;
    while i < tokens.len() {
        let TokenKind::HeadingMarker { level: open } = tokens[i].kind else {
            i += 1;
            continue;
        };
        // Find the closing marker before the next newline.
        let mut j = i + 1;
        let mut close: Option<(usize, usize)> = None;
        while j < tokens.len() && tokens[j].kind != TokenKind::Newline {
            if let TokenKind::HeadingMarker { level } = tokens[j].kind {
                close = Some((j, level));
            }
            j += 1;
        }
        match close {
            Some((cj, clevel)) if clevel != open => {
                let span = tokens[i].span.start..tokens[cj].span.end;
                let title = input[tokens[i].span.end..tokens[cj].span.start]
                    .trim()
                    .to_string();
                let eq = "=".repeat(open);
                out.push(
                    Diagnostic::new(
                        "SW005",
                        Severity::Error,
                        format!(
                            "heading opens with {open} `=` but closes with {clevel}; \
                             the level is ambiguous"
                        ),
                        span.clone(),
                    )
                    .with_fix(Fix {
                        span,
                        replacement: format!("{eq} {title} {eq}"),
                        // Which level the author meant is a guess; we keep the
                        // opening run, but that could be the wrong choice.
                        applicability: Applicability::Unsafe,
                        description: format!("make both runs {open} `=` long"),
                    }),
                );
            }
            None => {
                out.push(Diagnostic::new(
                    "SW005",
                    Severity::Error,
                    "heading has no closing `=`",
                    tokens[i].span.clone(),
                ));
            }
            _ => {}
        }
        i = j.max(i + 1);
    }
}

// ---------------------------------------------------------------------------
// SW006 — image parameters
// ---------------------------------------------------------------------------

fn image_params(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    for t in tokens {
        if t.kind
            != (TokenKind::Link {
                kind: LinkKind::Image,
            })
        {
            continue;
        }
        let full = t.text(input);
        let inner = full.trim_start_matches('[').trim_end_matches(']');
        // Byte offset of `inner` within the document.
        let base = t.span.start + (full.len() - full.trim_start_matches('[').len());
        let mut at = 0usize;
        for (n, part) in inner.split('|').enumerate() {
            let start = base + at;
            at += part.len() + 1;
            if n == 0 {
                continue; // the image name itself
            }
            let key_raw = part.split('=').next().unwrap_or("");
            let key = key_raw.trim().to_ascii_lowercase();
            if key.is_empty() || IMAGE_PARAMS.contains(&key.as_str()) {
                continue;
            }
            let lead = key_raw.len() - key_raw.trim_start().len();
            out.push(Diagnostic::new(
                "SW006",
                Severity::Error,
                format!(
                    "unknown `[[Image:]]` parameter `{}`; allowed: {}",
                    key.trim(),
                    IMAGE_PARAMS.join(", ")
                ),
                start + lead..start + lead + key_raw.trim().len(),
            ));
        }
    }
}

// ---------------------------------------------------------------------------
// SW007 — bracket balance
// ---------------------------------------------------------------------------

fn brackets(tokens: &[Token], out: &mut Vec<Diagnostic>) {
    for t in tokens.iter().filter(|t| !is_opaque(t)) {
        if let TokenKind::DanglingBracket { open } = t.kind {
            out.push(Diagnostic::new(
                "SW007",
                Severity::Error,
                if open {
                    "`[[` with no closing `]]`"
                } else {
                    "`]]` with no opening `[[`"
                },
                t.span.clone(),
            ));
        }
    }
}

// ---------------------------------------------------------------------------
// SW008 — empty list items
// ---------------------------------------------------------------------------

fn empty_list_items(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    for (n, t) in tokens.iter().enumerate() {
        if t.kind != TokenKind::ListMarker {
            continue;
        }
        // Everything up to the newline must be blank for the item to be empty.
        let mut j = n + 1;
        let mut empty = true;
        let mut end = t.span.end;
        while j < tokens.len() && tokens[j].kind != TokenKind::Newline {
            if !tokens[j].text(input).trim().is_empty() {
                empty = false;
                break;
            }
            end = tokens[j].span.end;
            j += 1;
        }
        if empty {
            out.push(
                Diagnostic::new(
                    "SW008",
                    Severity::Warning,
                    "list item has no content",
                    t.span.start..end,
                )
                .with_fix(Fix {
                    span: t.span.start..end,
                    replacement: String::new(),
                    applicability: Applicability::Safe,
                    description: "remove the empty list item".into(),
                }),
            );
        }
    }
}

// ---------------------------------------------------------------------------
// SW009 / SW010 — Markdown written by mistake
// ---------------------------------------------------------------------------

/// Detect Markdown link and bold syntax in text runs.
///
/// Only `Text` tokens are examined, so `[[Page|text]]`, `[http://… label]` and
/// anything inside `<code>` cannot trigger these.
fn markdown_syntax(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    for t in tokens {
        if t.kind != TokenKind::Text {
            continue;
        }
        let s = t.text(input);

        // [label](url)
        let bytes = s.as_bytes();
        let mut k = 0usize;
        while k < bytes.len() {
            if bytes[k] != b'[' {
                k += 1;
                continue;
            }
            let Some(rb) = s[k..].find(']').map(|p| k + p) else {
                break;
            };
            if s.as_bytes().get(rb + 1) != Some(&b'(') {
                k += 1;
                continue;
            }
            let Some(rp) = s[rb..].find(')').map(|p| rb + p) else {
                break;
            };
            let label = &s[k + 1..rb];
            let url = &s[rb + 2..rp];
            if label.is_empty() || url.is_empty() || url.contains(' ') {
                k = rb + 1;
                continue;
            }
            let span = t.span.start + k..t.span.start + rp + 1;
            out.push(
                Diagnostic::new(
                    "SW009",
                    Severity::Error,
                    "Markdown link syntax; SUMO uses `[url label]` or `[[Page|text]]`",
                    span.clone(),
                )
                .with_fix(Fix {
                    span,
                    replacement: if url.starts_with("http") {
                        format!("[{url} {label}]")
                    } else {
                        format!("[[{url}|{label}]]")
                    },
                    applicability: Applicability::Safe,
                    description: "rewrite as wiki link syntax".into(),
                }),
            );
            k = rp + 1;
        }

        // **bold**
        let mut k = 0usize;
        while let Some(p) = s[k..].find("**").map(|p| k + p) {
            let Some(q) = s[p + 2..].find("**").map(|x| p + 2 + x) else {
                break;
            };
            let inner = &s[p + 2..q];
            if inner.is_empty() || inner.contains('\n') || inner.contains('*') {
                k = p + 2;
                continue;
            }
            let span = t.span.start + p..t.span.start + q + 2;
            out.push(
                Diagnostic::new(
                    "SW010",
                    Severity::Error,
                    "Markdown bold syntax; SUMO uses `'''bold'''`",
                    span.clone(),
                )
                .with_fix(Fix {
                    span,
                    replacement: format!("'''{inner}'''"),
                    applicability: Applicability::Safe,
                    description: "rewrite as `'''bold'''`".into(),
                }),
            );
            k = q + 2;
        }
    }
}

// ---------------------------------------------------------------------------
// SW011 — empty macro arguments
// ---------------------------------------------------------------------------

fn empty_macros(input: &str, tokens: &[Token], out: &mut Vec<Diagnostic>) {
    for (n, t) in tokens.iter().enumerate() {
        let TokenKind::MacroOpen { kind } = t.kind else {
            continue;
        };
        // Scan to the matching MacroClose, checking for any real content.
        let mut has_content = false;
        let mut end = t.span.end;
        for u in &tokens[n + 1..] {
            end = u.span.end;
            if u.kind == TokenKind::MacroClose {
                break;
            }
            if !u.text(input).trim().is_empty() {
                has_content = true;
            }
        }
        if !has_content {
            let name = match kind {
                MacroKind::Key => "key",
                MacroKind::Button => "button",
                MacroKind::Menu => "menu",
                MacroKind::Filepath => "filepath",
                MacroKind::Pref => "pref",
            };
            out.push(Diagnostic::new(
                "SW011",
                Severity::Warning,
                format!("`{{{name}}}` has an empty argument"),
                t.span.start..end,
            ));
        }
    }
}

/// Names of opaque region kinds, for diagnostics and tests.
pub fn opaque_name(o: Opaque) -> &'static str {
    match o {
        Opaque::Nowiki => "nowiki",
        Opaque::Preformatted => "preformatted",
        Opaque::Pre => "pre",
        Opaque::Comment => "comment",
    }
}
