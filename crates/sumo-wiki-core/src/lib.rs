/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Linting for SUMO (support.mozilla.org) Knowledge Base wiki markup.
//!
//! This crate is deliberately **I/O-free**: no filesystem, no network, no async
//! runtime, no dependencies. That is what lets the same code back a native CLI, an
//! LSP server, and a WASM build for the browser without a second implementation.
//!
//! ```
//! let doc = sumo_wiki_core::Document::parse("{for win}unclosed");
//! assert_eq!(doc.reprint(), "{for win}unclosed");      // lossless
//! assert_eq!(doc.diagnostics()[0].code, "SW001");      // and it lints
//! ```
//!
//! The markup is Kitsune's own wiki dialect, **not** Markdown. See `CLAUDE.md`.

pub mod diagnostic;
pub mod lexer;
pub mod rules;

pub use diagnostic::{line_col, Applicability, Diagnostic, Fix, LineCol, Severity};
pub use lexer::{lex, LinkKind, MacroKind, Opaque, Token, TokenKind};

/// A parsed document: the source, plus tokens that tile it exactly.
#[derive(Debug, Clone)]
pub struct Document {
    source: String,
    tokens: Vec<Token>,
}

impl Document {
    pub fn parse(source: impl Into<String>) -> Self {
        let source = source.into();
        let tokens = lex(&source);
        Self { source, tokens }
    }

    pub fn source(&self) -> &str {
        &self.source
    }

    pub fn tokens(&self) -> &[Token] {
        &self.tokens
    }

    /// Reassemble the document from its tokens.
    ///
    /// This is byte-identical to [`Document::source`] for **every** input — the
    /// property the formatter depends on, and the one the corpus test enforces
    /// over every article in `corpus/en-US`.
    pub fn reprint(&self) -> String {
        let mut s = String::with_capacity(self.source.len());
        for t in &self.tokens {
            s.push_str(t.text(&self.source));
        }
        s
    }

    /// True if the token stream covers the source exactly, with no gaps.
    pub fn is_lossless(&self) -> bool {
        lexer::tiles(&self.tokens, self.source.len()) && self.reprint() == self.source
    }

    pub fn diagnostics(&self) -> Vec<Diagnostic> {
        rules::check(&self.source, &self.tokens)
    }

    /// Apply fixes and return the rewritten source.
    ///
    /// Only `Safe` fixes are applied unless `include_unsafe` is set. Overlapping
    /// fixes are dropped rather than merged: applying two edits to the same bytes
    /// would produce something neither rule intended.
    pub fn apply_fixes(&self, include_unsafe: bool) -> (String, usize) {
        let mut fixes: Vec<Fix> = self
            .diagnostics()
            .into_iter()
            .filter_map(|d| d.fix)
            .filter(|f| include_unsafe || f.applicability == Applicability::Safe)
            .collect();
        fixes.sort_by_key(|f| (f.span.start, f.span.end));

        let mut out = String::with_capacity(self.source.len());
        let mut at = 0usize;
        let mut applied = 0usize;
        for f in fixes {
            if f.span.start < at {
                continue; // overlaps an already-applied fix
            }
            out.push_str(&self.source[at..f.span.start]);
            out.push_str(&f.replacement);
            at = f.span.end;
            applied += 1;
        }
        out.push_str(&self.source[at..]);
        (out, applied)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Round-trip is the property everything else rests on.
    fn round_trips(src: &str) {
        let d = Document::parse(src);
        assert!(
            d.is_lossless(),
            "not lossless: {src:?}\ntokens: {:#?}",
            d.tokens()
        );
    }

    #[test]
    fn round_trips_representative_markup() {
        for src in [
            "",
            "\n",
            "plain text",
            "= Heading =\n",
            "=Tight=\n",
            "== Level two ==\n",
            "'''bold''' and ''italic''\n",
            "'''''bold italic'''''\n",
            "{for win,mac}Tools{/for}{for linux}Edit{/for}\n",
            "{note}'''NOTE''': careful{/note}\n",
            "{warning}danger{/warning}\n",
            "{key Ctrl+T} {button OK} {menu Settings} {filepath /tmp} {pref foo.bar}\n",
            "[[Image:Foo.png|width=300|align=left]]\n",
            "[[Page Title|text]] [[T:Template]] [[Video:https://x]] [[UI:details_start]]\n",
            "[http://example.com Label]\n",
            "__TOC__\n----\n",
            "* a\n*# b\n; def\n",
            "<nowiki>{for this} '''not markup'''</nowiki>\n",
            "<code>=== registry ===</code>\n",
            "<!-- {note} ignored -->\n",
            "text<br>more<strong>x</strong>\n",
            "{| \n|+ cap\n!a!!b\n|-\n|c||d\n|}\n",
            "unterminated <code>forever",
            "trailing spaces   \n\ttab\r\n",
            "héllo — ünïcode ✓ 日本語\n",
            "{for}bare condition{/for}\n",
        ] {
            round_trips(src);
        }
    }

    /// Which regions suppress markup was settled by comparing against Kitsune's
    /// own rendered output, not by assumption. An earlier version of this test
    /// asserted that `<code>` suppresses markup; the oracle disproved it.
    #[test]
    fn opaque_regions_match_kitsune_semantics() {
        // <nowiki> and <pre> do suppress markup.
        for src in ["<nowiki>{note}x</nowiki>\n", "<pre>{note}x</pre>\n"] {
            let d = Document::parse(src);
            assert!(
                d.diagnostics().is_empty(),
                "{src:?} -> {:?}",
                d.diagnostics()
            );
        }

        // A space-indented line is preformatted, so an indented `.reg` sample is
        // not a heading. This is switching-thunderbird's shape.
        let d = Document::parse(" === Registry file ===\n Version 5.00\n ===\n");
        assert!(d.diagnostics().is_empty(), "{:?}", d.diagnostics());

        // <code> does NOT suppress markup: a {/note} inside it closes a real note
        // block, so this is balanced and must be clean.
        let d = Document::parse("{note}real<code>{/note}</code>\n");
        assert!(d.diagnostics().is_empty(), "{:?}", d.diagnostics());
        // And an unpaired closer inside <code> must still be reported.
        let d = Document::parse("<code>{/note}</code>\n");
        assert!(
            d.diagnostics().iter().any(|x| x.code == "SW002"),
            "{:?}",
            d.diagnostics()
        );
    }

    /// Markup inside an external link label is processed by Kitsune, so a stray
    /// marker there must not be hidden by treating the link as a single atom.
    #[test]
    fn bold_inside_external_link_label_is_counted() {
        let src = "* Configure [https://x.example/a Thunderbird Send'''] for files.\n";
        let d = Document::parse(src);
        assert!(
            d.diagnostics().iter().any(|x| x.code == "SW004"),
            "{:?}",
            d.diagnostics()
        );
    }

    /// Nested `{for}` inside `{menu …}` is real corpus markup and must pair up.
    #[test]
    fn for_blocks_nested_in_macros_pair_correctly() {
        let d = Document::parse(
            "{menu {for win}Open Containing Folder{/for}{for mac}Show in Finder{/for}}\n",
        );
        assert!(d.is_lossless());
        assert!(d.diagnostics().is_empty(), "{:?}", d.diagnostics());
    }

    #[test]
    fn multiline_bold_italic_is_balanced() {
        // Real corpus shape: '''''intro … list items …''''' across three lines.
        let d = Document::parse("'''''Based on information from\n* [[A]]\n* [http://x B]'''''\n");
        assert!(
            !d.diagnostics().iter().any(|x| x.code == "SW004"),
            "{:?}",
            d.diagnostics()
        );
    }

    #[test]
    fn detects_unbalanced_bold() {
        let d = Document::parse("* '''Authentication method: '''OAuth2'''\n");
        let codes: Vec<_> = d.diagnostics().iter().map(|x| x.code).collect();
        assert!(codes.contains(&"SW004"), "{codes:?}");
    }

    #[test]
    fn detects_unclosed_blocks() {
        for (src, code) in [
            ("{for win}x\n", "SW001"),
            ("{/for}\n", "SW001"),
            ("{note}x\n", "SW002"),
            ("{warning}x\n", "SW003"),
        ] {
            let d = Document::parse(src);
            assert!(
                d.diagnostics().iter().any(|x| x.code == code),
                "{src:?} should report {code}, got {:?}",
                d.diagnostics()
            );
        }
    }

    #[test]
    fn detects_bad_image_param() {
        let d = Document::parse("[[Image:a.png|width=300|bogus=7]]\n");
        let ds = d.diagnostics();
        let sw006: Vec<_> = ds.iter().filter(|x| x.code == "SW006").collect();
        assert_eq!(sw006.len(), 1, "only `bogus` is unknown: {ds:?}");
        assert!(sw006[0].message.contains("`bogus`"), "{ds:?}");
        // The span must point at the offending key, not the whole link.
        assert_eq!(&d.source()[sw006[0].span.clone()], "bogus");
    }

    #[test]
    fn markdown_syntax_is_fixed_safely() {
        let d = Document::parse("see [label](http://example.com) and **bold**\n");
        let (fixed, n) = d.apply_fixes(false);
        assert_eq!(n, 2, "{:?}", d.diagnostics());
        assert_eq!(fixed, "see [http://example.com label] and '''bold'''\n");
        // The fixed output must itself be clean.
        assert!(Document::parse(&fixed).diagnostics().is_empty());
    }

    #[test]
    fn asymmetric_heading_reported_but_fix_is_unsafe() {
        let d = Document::parse("==Asymmetric ===\n");
        let ds = d.diagnostics();
        let sw005 = ds.iter().find(|x| x.code == "SW005").expect("SW005");
        assert_eq!(
            sw005.fix.as_ref().unwrap().applicability,
            Applicability::Unsafe
        );
        // Not applied by default, precisely because the intended level is a guess.
        assert_eq!(d.apply_fixes(false).1, 0);
    }

    #[test]
    fn fixes_never_break_round_trip() {
        let d = Document::parse("* \n**bold** [x](http://y)\n");
        let (fixed, _) = d.apply_fixes(false);
        assert!(Document::parse(&fixed).is_lossless());
    }
}
