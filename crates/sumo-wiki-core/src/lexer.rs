/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Lossless lexer for SUMO wiki markup.
//!
//! The tokens returned by [`lex`] **tile the input exactly**: their spans are
//! contiguous, start at 0, end at `input.len()`, and never overlap. Concatenating
//! their text reproduces the input byte for byte. That property is what makes a
//! formatter possible — anything the formatter does not deliberately change is
//! reprinted untouched — and it is enforced by a debug assertion here plus a
//! property test over every article in the corpus.
//!
//! Scope was chosen by measured frequency in the real Thunderbird KB corpus, not
//! from the spec. See `corpus/report.md`.

use core::ops::Range;

/// Regions where wiki markup is **not** interpreted.
///
/// Membership here was settled by comparing against Kitsune's own rendered
/// output, not by assumption — an earlier version wrongly included `<code>`.
/// A token stream can mark a region opaque while still keeping its bytes, which
/// is precisely what a regex cannot do: blanking `<code>` to stop a literal
/// `===` being read as a heading also deleted real `{/note}` closers living
/// inside code spans, inventing "unclosed note" errors.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Opaque {
    Nowiki,
    Pre,
    Comment,
    /// A line beginning with a space. Wiki markup renders these preformatted and
    /// does not interpret markup inside them. Verified against Kitsune's output:
    /// in `switching-thunderbird`, space-indented `.reg` sample lines containing
    /// `=== Registry file … ===` render inside `<pre>` with the `===` literal and
    /// contribute none of that page's 14 headings.
    Preformatted,
}

/// Which wiki-link family a `[[...]]` construct belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LinkKind {
    Image,
    Video,
    Ui,
    Template,
    Include,
    /// Ordinary internal article link, `[[Page]]` or `[[Page|text]]`.
    Internal,
}

/// Inline macros of the form `{name arg}`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MacroKind {
    Key,
    Button,
    Menu,
    Filepath,
    Pref,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TokenKind {
    Text,
    /// Exactly one `\n`. `\r` is kept in the preceding `Text` so round-trip holds.
    Newline,
    /// A run of `=` at the start or end of a heading line.
    HeadingMarker {
        level: usize,
    },
    /// `'''`
    Bold,
    /// `''` not part of a longer quote run.
    Italic,
    /// `{for}` or `{for cond}` — the condition text, if any.
    ForOpen,
    /// `{/for}`
    ForClose,
    /// `{note}` / `{warning}`
    BlockOpen {
        warning: bool,
    },
    /// `{/note}` / `{/warning}`
    BlockClose {
        warning: bool,
    },
    /// The `{name ` opener of an inline macro. Macros are lexed as a pair rather
    /// than one token because real articles nest `{for}` blocks inside them:
    /// `{menu {for win}Open Containing Folder{/for}{for mac}Show in Finder{/for}}`.
    /// Grabbing to the first `}` would swallow the `{for}` opener and report 59
    /// phantom unmatched `{/for}` across the corpus. Kitsune sidesteps this by
    /// running `strip_fors()` before macro matching; lexing a pair is equivalent.
    MacroOpen {
        kind: MacroKind,
    },
    /// The `}` closing a [`TokenKind::MacroOpen`].
    MacroClose,
    /// A complete `[[...]]` construct.
    Link {
        kind: LinkKind,
    },
    /// `[[` or `]]` that has no partner — kept as its own token so rules can report it.
    DanglingBracket {
        open: bool,
    },
    /// A complete `[http://url]` with no label.
    ExternalLink,
    /// The `[url ` opener of a labelled external link.
    ///
    /// Labelled links are a pair so markup inside the label stays visible.
    /// Kitsune processes it: the rendered output for
    /// `install-thunderbird-pro-add-thunderbird-desktop` contains a `<strong>`
    /// produced by a stray `'''` inside a link label, which an atomic token would
    /// have hidden from the bold-balance rule.
    ExternalLinkOpen,
    /// The `]` closing an [`TokenKind::ExternalLinkOpen`].
    ExternalLinkClose,
    /// A raw HTML tag such as `<br>` or `</strong>`. Common in the corpus (577
    /// occurrences), so it is tokenised rather than rejected.
    HtmlTag,
    Toc,
    /// `----` or longer, alone on a line.
    HorizontalRule,
    /// Leading `*`/`#` run, or a leading `;`.
    ListMarker,
    /// Opaque region, including its delimiters.
    Opaque {
        kind: Opaque,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Token {
    pub kind: TokenKind,
    pub span: Range<usize>,
}

impl Token {
    pub fn text<'a>(&self, input: &'a str) -> &'a str {
        &input[self.span.clone()]
    }
}

/// Regions that suppress wiki markup, with their delimiters.
///
/// `<code>` is deliberately absent. Verified against Kitsune's own rendered
/// output: in `how-subscribe-news-feeds-and-blogs`, two `{/note}` closers that
/// sit inside `<code>` spans are consumed as real note closers (8 `{note}`
/// produce 8 `<div class="note">`, and no literal `{note}` survives). `<code>`
/// is ordinary inline HTML, not a parser extension tag. `<pre>` does suppress —
/// a `.reg` example's literal `===` stays literal in the rendered page.
const OPAQUE: &[(&str, &str, Opaque)] = &[
    ("<!--", "-->", Opaque::Comment),
    ("<nowiki>", "</nowiki>", Opaque::Nowiki),
    ("<pre>", "</pre>", Opaque::Pre),
];

const MACROS: &[(&str, MacroKind)] = &[
    ("{key ", MacroKind::Key),
    ("{button ", MacroKind::Button),
    ("{menu ", MacroKind::Menu),
    ("{filepath ", MacroKind::Filepath),
    ("{pref ", MacroKind::Pref),
];

/// Tokenise `input`. The result always tiles `input` exactly.
pub fn lex(input: &str) -> Vec<Token> {
    let mut out: Vec<Token> = Vec::new();
    let b = input.as_bytes();
    let mut i = 0usize;
    // Byte offset of the current line's start, for line-anchored constructs.
    let mut line_start = 0usize;
    // Text accumulates until a delimiter is found, then is flushed as one token.
    let mut text_from = 0usize;
    // How many `{name ` macro openers are currently unclosed.
    let mut macro_depth = 0usize;
    // How many labelled external links are currently unclosed.
    let mut ext_depth = 0usize;

    macro_rules! flush {
        ($upto:expr) => {
            if $upto > text_from {
                out.push(Token {
                    kind: TokenKind::Text,
                    span: text_from..$upto,
                });
            }
        };
    }

    while i < b.len() {
        // --- opaque regions -------------------------------------------------
        if b[i] == b'<' {
            if let Some((open, close, kind)) = OPAQUE
                .iter()
                .find(|(o, _, _)| starts_with_ci(&input[i..], o))
                .map(|(o, c, k)| (*o, *c, *k))
            {
                flush!(i);
                let body = i + open.len();
                let end = find_ci(input, close, body)
                    .map(|p| p + close.len())
                    .unwrap_or(b.len()); // unterminated: swallow to EOF, still lossless
                out.push(Token {
                    kind: TokenKind::Opaque { kind },
                    span: i..end,
                });
                i = end;
                text_from = i;
                continue;
            }
            // --- raw HTML tag ------------------------------------------------
            if let Some(end) = html_tag_end(input, i) {
                flush!(i);
                out.push(Token {
                    kind: TokenKind::HtmlTag,
                    span: i..end,
                });
                i = end;
                text_from = i;
                continue;
            }
        }

        // --- line-anchored constructs ---------------------------------------
        if i == line_start {
            let rest = &input[i..];
            let line_end = rest.find('\n').map(|p| i + p).unwrap_or(b.len());
            let line = &input[i..line_end];
            let indent = line.len() - line.trim_start().len();
            let trimmed = line.trim();

            // Preformatted: a line starting with a space. Must be tested before
            // headings, or a space-indented code sample looks like markup.
            if line.starts_with(' ') && !trimmed.is_empty() {
                flush!(i);
                out.push(Token {
                    kind: TokenKind::Opaque {
                        kind: Opaque::Preformatted,
                    },
                    span: i..line_end,
                });
                i = line_end;
                text_from = i;
                continue;
            }

            // Horizontal rule: four or more dashes, nothing else.
            if trimmed.len() >= 4 && trimmed.bytes().all(|c| c == b'-') {
                flush!(i);
                if indent > 0 {
                    out.push(Token {
                        kind: TokenKind::Text,
                        span: i..i + indent,
                    });
                }
                out.push(Token {
                    kind: TokenKind::HorizontalRule,
                    span: i + indent..line_end,
                });
                i = line_end;
                text_from = i;
                continue;
            }

            // Heading: a run of '=' at both ends with no '=' inside.
            if let Some((open, close)) = heading_markers(line) {
                flush!(i);
                if indent > 0 {
                    out.push(Token {
                        kind: TokenKind::Text,
                        span: i..i + indent,
                    });
                }
                let s = i + indent;
                out.push(Token {
                    kind: TokenKind::HeadingMarker { level: open },
                    span: s..s + open,
                });
                // The inner text is lexed normally, so inline markup inside a
                // heading is still tokenised; the closing run is emitted when we
                // reach it, detected by position.
                i = s + open;
                text_from = i;
                let _ = close;
                continue;
            }

            // List / definition marker.
            let marker_len = line[indent..]
                .bytes()
                .take_while(|c| matches!(c, b'*' | b'#'))
                .count();
            let marker_len = if marker_len > 0 {
                marker_len
            } else if line[indent..].starts_with(';') {
                1
            } else {
                0
            };
            if marker_len > 0 {
                flush!(i);
                if indent > 0 {
                    out.push(Token {
                        kind: TokenKind::Text,
                        span: i..i + indent,
                    });
                }
                out.push(Token {
                    kind: TokenKind::ListMarker,
                    span: i + indent..i + indent + marker_len,
                });
                i += indent + marker_len;
                text_from = i;
                continue;
            }
        }

        // Closing heading run: '=' run that reaches end of line.
        if b[i] == b'=' && in_heading_tail(input, i) {
            let run = input[i..].bytes().take_while(|c| *c == b'=').count();
            flush!(i);
            out.push(Token {
                kind: TokenKind::HeadingMarker { level: run },
                span: i..i + run,
            });
            i += run;
            text_from = i;
            continue;
        }

        // --- braces ----------------------------------------------------------
        if b[i] == b'{' {
            let rest = &input[i..];
            let mut hit: Option<(TokenKind, usize)> = None;
            if rest.starts_with("{/for}") {
                hit = Some((TokenKind::ForClose, 6));
            } else if rest.starts_with("{note}") {
                hit = Some((TokenKind::BlockOpen { warning: false }, 6));
            } else if rest.starts_with("{warning}") {
                hit = Some((TokenKind::BlockOpen { warning: true }, 9));
            } else if rest.starts_with("{/note}") {
                hit = Some((TokenKind::BlockClose { warning: false }, 7));
            } else if rest.starts_with("{/warning}") {
                hit = Some((TokenKind::BlockClose { warning: true }, 10));
            } else if rest.starts_with("{for}") || rest.starts_with("{for ") {
                // The condition may contain commas, spaces, '=' and "not".
                hit = rest.find('}').map(|c| (TokenKind::ForOpen, c + 1));
            } else if let Some((lit, kind)) = MACROS
                .iter()
                .find(|(l, _)| rest.starts_with(*l))
                .map(|(l, k)| (*l, *k))
            {
                // Emit just the opener; the argument is lexed normally and the
                // matching `}` becomes a MacroClose below.
                macro_depth += 1;
                hit = Some((TokenKind::MacroOpen { kind }, lit.len()));
            }
            if let Some((kind, len)) = hit {
                flush!(i);
                out.push(Token {
                    kind,
                    span: i..i + len,
                });
                i += len;
                text_from = i;
                continue;
            }
        }

        if b[i] == b'}' && macro_depth > 0 {
            flush!(i);
            out.push(Token {
                kind: TokenKind::MacroClose,
                span: i..i + 1,
            });
            macro_depth -= 1;
            i += 1;
            text_from = i;
            continue;
        }

        // --- links -----------------------------------------------------------
        if b[i] == b'[' && b.get(i + 1) == Some(&b'[') {
            if let Some(rel) = input[i..].find("]]") {
                let end = i + rel + 2;
                let inner = &input[i + 2..i + rel];
                flush!(i);
                out.push(Token {
                    kind: TokenKind::Link {
                        kind: link_kind(inner),
                    },
                    span: i..end,
                });
                i = end;
                text_from = i;
                continue;
            }
            flush!(i);
            out.push(Token {
                kind: TokenKind::DanglingBracket { open: true },
                span: i..i + 2,
            });
            i += 2;
            text_from = i;
            continue;
        }
        if b[i] == b']' && b.get(i + 1) == Some(&b']') {
            flush!(i);
            out.push(Token {
                kind: TokenKind::DanglingBracket { open: false },
                span: i..i + 2,
            });
            i += 2;
            text_from = i;
            continue;
        }
        if b[i] == b'['
            && (starts_with_ci(&input[i..], "[http://") || starts_with_ci(&input[i..], "[https://"))
        {
            if let Some(rel) = input[i..].find(']') {
                flush!(i);
                match input[i..i + rel].find(' ') {
                    // `[url label]`: emit `[url ` and lex the label normally.
                    Some(sp) => {
                        out.push(Token {
                            kind: TokenKind::ExternalLinkOpen,
                            span: i..i + sp + 1,
                        });
                        ext_depth += 1;
                        i += sp + 1;
                    }
                    // `[url]` has no label, so there is nothing inside to lex.
                    None => {
                        out.push(Token {
                            kind: TokenKind::ExternalLink,
                            span: i..i + rel + 1,
                        });
                        i += rel + 1;
                    }
                }
                text_from = i;
                continue;
            }
        }
        if b[i] == b']' && ext_depth > 0 {
            flush!(i);
            out.push(Token {
                kind: TokenKind::ExternalLinkClose,
                span: i..i + 1,
            });
            ext_depth -= 1;
            i += 1;
            text_from = i;
            continue;
        }

        // --- emphasis --------------------------------------------------------
        if b[i] == b'\'' {
            let run = input[i..].bytes().take_while(|c| *c == b'\'').count();
            // '''''bold-italic''''' is a Bold followed by an Italic; matches how
            // wikimarkup consumes quote runs, and keeps pairing counts sane.
            if run >= 3 {
                flush!(i);
                out.push(Token {
                    kind: TokenKind::Bold,
                    span: i..i + 3,
                });
                i += 3;
                text_from = i;
                continue;
            }
            if run == 2 {
                flush!(i);
                out.push(Token {
                    kind: TokenKind::Italic,
                    span: i..i + 2,
                });
                i += 2;
                text_from = i;
                continue;
            }
        }

        // --- misc ------------------------------------------------------------
        if input[i..].starts_with("__TOC__") {
            flush!(i);
            out.push(Token {
                kind: TokenKind::Toc,
                span: i..i + 7,
            });
            i += 7;
            text_from = i;
            continue;
        }
        if b[i] == b'\n' {
            flush!(i);
            out.push(Token {
                kind: TokenKind::Newline,
                span: i..i + 1,
            });
            i += 1;
            text_from = i;
            line_start = i;
            continue;
        }

        // Advance by one *character*, not one byte: the corpus contains Arabic,
        // Japanese, em-dashes and accented Latin, and a byte-wise bump lands
        // mid-codepoint and panics on the next slice.
        i += input[i..].chars().next().map_or(1, char::len_utf8);
    }
    flush!(b.len());

    debug_assert!(
        tiles(&out, input.len()),
        "lexer must tile the input exactly"
    );
    out
}

/// True if the tokens are contiguous and cover exactly `0..len`.
pub fn tiles(tokens: &[Token], len: usize) -> bool {
    let mut at = 0usize;
    for t in tokens {
        if t.span.start != at || t.span.end < t.span.start {
            return false;
        }
        at = t.span.end;
    }
    at == len
}

/// ASCII case-insensitive `starts_with`, without allocating.
fn starts_with_ci(hay: &str, needle: &str) -> bool {
    let (h, n) = (hay.as_bytes(), needle.as_bytes());
    h.len() >= n.len()
        && h[..n.len()]
            .iter()
            .zip(n)
            .all(|(a, b)| a.eq_ignore_ascii_case(b))
}

/// ASCII case-insensitive `find` from `from`, without allocating. An earlier
/// version lowercased the whole input on every `<`, which is quadratic.
fn find_ci(hay: &str, needle: &str, from: usize) -> Option<usize> {
    let (h, n) = (hay.as_bytes(), needle.as_bytes());
    if n.is_empty() || h.len() < n.len() {
        return None;
    }
    (from..=h.len() - n.len()).find(|&p| {
        h[p..p + n.len()]
            .iter()
            .zip(n)
            .all(|(a, b)| a.eq_ignore_ascii_case(b))
    })
}

/// End offset of an HTML tag starting at `i`, if it looks like one.
fn html_tag_end(input: &str, i: usize) -> Option<usize> {
    let rest = &input[i + 1..];
    let body = rest.strip_prefix('/').unwrap_or(rest);
    if !body.starts_with(|c: char| c.is_ascii_alphabetic()) {
        return None;
    }
    let rel = rest.find('>')?;
    // Reject anything containing a newline or '<': far more likely to be prose.
    let inner = &rest[..rel];
    if inner.contains('\n') || inner.contains('<') {
        return None;
    }
    Some(i + 1 + rel + 1)
}

/// If `line` is a heading, return the lengths of its opening and closing `=` runs.
fn heading_markers(line: &str) -> Option<(usize, usize)> {
    let t = line.trim();
    if !t.starts_with('=') || t.len() < 2 {
        return None;
    }
    let open = t.bytes().take_while(|c| *c == b'=').count();
    let close = t.bytes().rev().take_while(|c| *c == b'=').count();
    if open == t.len() {
        return None; // a line of only '=' is not a heading
    }
    let inner = &t[open..t.len() - close];
    if inner.contains('=') {
        return None;
    }
    Some((open, close))
}

/// True if the `=` run at `i` closes a heading: only `=` then whitespace to EOL.
fn in_heading_tail(input: &str, i: usize) -> bool {
    let line_end = input[i..].find('\n').map(|p| i + p).unwrap_or(input.len());
    let tail = &input[i..line_end];
    !tail.is_empty()
        && tail.trim_end().bytes().all(|c| c == b'=')
        && input[..i]
            .lines()
            .last()
            .is_some_and(|l| l.trim_start().starts_with('='))
}

fn link_kind(inner: &str) -> LinkKind {
    let head = inner.split('|').next().unwrap_or("");
    let name = head
        .split(':')
        .next()
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase();
    match name.as_str() {
        "image" => LinkKind::Image,
        "video" | "v" => LinkKind::Video,
        "ui" => LinkKind::Ui,
        "template" | "t" => LinkKind::Template,
        "include" | "i" => LinkKind::Include,
        _ => LinkKind::Internal,
    }
}
