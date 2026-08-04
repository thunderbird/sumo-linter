/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Phase 2: opinionated formatting.
//!
//! The guiding constraint is **churn avoidance**. Every source change, however
//! cosmetic, is surfaced to volunteer localizers who then have to look at it. A
//! formatter that rewrites 500 headings for no rendered difference spends other
//! people's time, so the default policy is the one that changes as little as
//! possible while still removing genuine inconsistency.
//!
//! Hence [`HeadingSpacing::PreserveDominant`] as the default: each article is
//! normalised to **its own** majority style. An article that already picks a lane
//! is left completely untouched. Measured on the corpus, 145 of 166 articles with
//! headings are already internally consistent, so they produce no diff at all;
//! only the 20 that contradict themselves are changed, at 43 headings total.
//!
//! This also means the `= H =` versus `=H=` question does not have to be settled
//! before phase 2 ships. When the community decides, set [`Style::heading_spacing`]
//! to [`HeadingSpacing::Spaced`] or [`HeadingSpacing::Tight`] and the same code
//! enforces it.

use crate::lexer::{Opaque, Token, TokenKind};

/// How `= Heading =` should be spaced.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum HeadingSpacing {
    /// Normalise each article to whichever style it already uses most. Articles
    /// that are already consistent are not modified. Ties are left alone.
    #[default]
    PreserveDominant,
    /// Always `= Heading =`.
    Spaced,
    /// Always `=Heading=`.
    Tight,
}

/// Phase-2 style options.
///
/// The derived default is deliberately the least invasive setting available:
/// per-article heading normalisation, and no whitespace changes at all.
#[derive(Debug, Clone, Copy, Default)]
pub struct Style {
    pub heading_spacing: HeadingSpacing,
    /// Strip trailing spaces and tabs from lines. **Off by default.**
    ///
    /// Measured on the corpus, this is the single largest source of churn:
    /// enabling it takes the proportion of articles modified from 15% to 64%
    /// (30 → 129 of 203), for no rendered difference whatsoever. Every one of
    /// those diffs lands in front of a volunteer localizer who has to look at a
    /// changed line and discover that nothing actually changed. Not worth it as a
    /// default; available for anyone who wants it on a file they are already
    /// editing heavily.
    ///
    /// Never applied inside `<pre>`, `<nowiki>` or space-indented preformatted
    /// lines, where trailing whitespace is content rather than sloppiness.
    pub trailing_whitespace: bool,
}

impl Style {
    /// The Thunderbird preset. Currently the defaults; kept as a named entry
    /// point so the community's heading decision lands in exactly one place.
    pub fn thunderbird() -> Self {
        Self::default()
    }
}

/// One heading found in the token stream.
struct Heading {
    /// Span covering the whole heading, opening marker through closing marker.
    span: core::ops::Range<usize>,
    /// Length of the opening `=` run.
    level: usize,
    /// Length of the closing `=` run.
    close_level: usize,
    /// The title, trimmed.
    title: String,
    /// Whether it is currently written with a space on both sides.
    spaced: bool,
}

fn headings(input: &str, tokens: &[Token]) -> Vec<Heading> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < tokens.len() {
        let TokenKind::HeadingMarker { level } = tokens[i].kind else {
            i += 1;
            continue;
        };
        let mut j = i + 1;
        let mut close: Option<usize> = None;
        while j < tokens.len() && tokens[j].kind != TokenKind::Newline {
            if let TokenKind::HeadingMarker { .. } = tokens[j].kind {
                close = Some(j);
            }
            j += 1;
        }
        if let Some(cj) = close {
            let TokenKind::HeadingMarker { level: close_level } = tokens[cj].kind else {
                unreachable!()
            };
            let inner = &input[tokens[i].span.end..tokens[cj].span.start];
            out.push(Heading {
                span: tokens[i].span.start..tokens[cj].span.end,
                level,
                close_level,
                title: inner.trim().to_string(),
                spaced: inner == format!(" {} ", inner.trim()),
            });
        }
        i = j.max(i + 1);
    }
    out
}

/// Byte ranges where formatting must not touch anything.
fn protected(tokens: &[Token]) -> Vec<core::ops::Range<usize>> {
    tokens
        .iter()
        .filter(|t| {
            matches!(
                t.kind,
                TokenKind::Opaque {
                    kind: Opaque::Pre | Opaque::Nowiki | Opaque::Preformatted
                }
            )
        })
        .map(|t| t.span.clone())
        .collect()
}

/// Apply `style` to `input`, given its tokens. Returns the formatted text.
///
/// Guarantees, both property-tested over the whole corpus:
///   - **Idempotent**: formatting twice equals formatting once.
///   - **No gratuitous churn**: an article already conforming is returned byte
///     for byte unchanged.
pub fn format(input: &str, tokens: &[Token], style: &Style) -> String {
    let hs = headings(input, tokens);

    // Decide the target heading style once per document.
    let want_spaced: Option<bool> = match style.heading_spacing {
        HeadingSpacing::Spaced => Some(true),
        HeadingSpacing::Tight => Some(false),
        HeadingSpacing::PreserveDominant => {
            let spaced = hs.iter().filter(|h| h.spaced).count();
            let tight = hs.len() - spaced;
            match spaced.cmp(&tight) {
                core::cmp::Ordering::Greater => Some(true),
                core::cmp::Ordering::Less => Some(false),
                // A tie gives no mandate, so change nothing rather than pick.
                core::cmp::Ordering::Equal => None,
            }
        }
    };

    // Rewrite headings first, working on byte spans.
    let mut edits: Vec<(core::ops::Range<usize>, String)> = Vec::new();
    if let Some(spaced) = want_spaced {
        for h in &hs {
            // An asymmetric heading is a phase-1 error (SW005) whose correct level
            // is a guess, so leave it for a human rather than silently choosing.
            if h.level != h.close_level {
                continue;
            }
            let eq = "=".repeat(h.level);
            let want = if spaced {
                format!("{eq} {} {eq}", h.title)
            } else {
                format!("{eq}{}{eq}", h.title)
            };
            if input[h.span.clone()] != want {
                edits.push((h.span.clone(), want));
            }
        }
    }

    let mut out = String::with_capacity(input.len());
    let mut at = 0usize;
    for (span, text) in &edits {
        if span.start < at {
            continue;
        }
        out.push_str(&input[at..span.start]);
        out.push_str(text);
        at = span.end;
    }
    out.push_str(&input[at..]);

    if style.trailing_whitespace {
        out = strip_trailing_whitespace(&out, input, &protected(tokens));
    }
    out
}

/// Remove trailing spaces and tabs, skipping protected regions.
///
/// Protected spans are byte ranges into the *original* input, so this is only
/// sound because heading rewrites never change the number of lines: a line's
/// index is stable even when its bytes shift.
fn strip_trailing_whitespace(
    text: &str,
    original: &str,
    protected_spans: &[core::ops::Range<usize>],
) -> String {
    // Which original line numbers fall inside a protected span.
    let mut protected_lines = std::collections::HashSet::new();
    for span in protected_spans {
        let first = original[..span.start]
            .bytes()
            .filter(|c| *c == b'\n')
            .count();
        let last = original[..span.end.min(original.len())]
            .bytes()
            .filter(|c| *c == b'\n')
            .count();
        for l in first..=last {
            protected_lines.insert(l);
        }
    }

    let ends_with_newline = text.ends_with('\n');
    let mut out: Vec<String> = Vec::new();
    for (n, line) in text.split('\n').enumerate() {
        if protected_lines.contains(&n) {
            out.push(line.to_string());
        } else {
            out.push(line.trim_end_matches([' ', '\t']).to_string());
        }
    }
    let mut s = out.join("\n");
    // `split('\n')` on "a\n" yields ["a", ""], so the join already restored the
    // final newline; guard the case where trimming removed it.
    if ends_with_newline && !s.ends_with('\n') {
        s.push('\n');
    }
    s
}
