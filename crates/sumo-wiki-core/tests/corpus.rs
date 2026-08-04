/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Property tests over the real Thunderbird KB corpus.
//!
//! These are the tests that matter. Hand-written cases only prove the lexer
//! handles markup I thought of; the corpus proves it handles markup Mozilla
//! contributors actually wrote. Skipped gracefully if the corpus is absent.

use std::path::{Path, PathBuf};
use sumo_wiki_core::Document;

fn corpus_files() -> Vec<PathBuf> {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpus/en-US");
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut v: Vec<PathBuf> = rd
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "wiki"))
        .collect();
    v.sort();
    v
}

/// Round-trip: reprinting an unmodified parse must be byte-identical.
///
/// This is the guarantee the phase-2 formatter rests on — it may only change what
/// it intends to change.
#[test]
fn round_trips_every_corpus_article() {
    let files = corpus_files();
    if files.is_empty() {
        eprintln!("corpus not present; skipping (run tools/scrape)");
        return;
    }
    let mut checked = 0;
    for f in &files {
        let src = std::fs::read_to_string(f).unwrap();
        let doc = Document::parse(&src);
        assert!(
            doc.is_lossless(),
            "round-trip failed for {}",
            f.file_name().unwrap().to_string_lossy()
        );
        checked += 1;
    }
    eprintln!("round-trip verified on {checked} corpus articles");
    assert!(checked >= 150, "expected the full corpus, saw {checked}");
}

/// Linting must never panic on real input, however odd.
#[test]
fn lints_every_corpus_article_without_panicking() {
    let mut total = 0usize;
    for f in corpus_files() {
        let src = std::fs::read_to_string(&f).unwrap();
        total += Document::parse(&src).diagnostics().len();
    }
    eprintln!("{total} diagnostics across the corpus");
}

/// Applying safe fixes must preserve losslessness and be idempotent: fixing
/// twice changes nothing the second time.
#[test]
fn safe_fixes_are_idempotent_on_the_corpus() {
    for f in corpus_files() {
        let src = std::fs::read_to_string(&f).unwrap();
        let name = f.file_name().unwrap().to_string_lossy().to_string();
        let (once, _) = Document::parse(&src).apply_fixes(false);
        assert!(
            Document::parse(&once).is_lossless(),
            "{name}: fixed output not lossless"
        );
        let (twice, n) = Document::parse(&once).apply_fixes(false);
        assert_eq!(n, 0, "{name}: still had {n} fixes on the second pass");
        assert_eq!(once, twice, "{name}: fixing is not idempotent");
    }
}

/// The committed known-bad fixture must parse and report its planted errors.
#[test]
fn known_bad_fixture_reports_errors() {
    let p =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/selftest-known-bad.wiki");
    let Ok(src) = std::fs::read_to_string(p) else {
        return;
    };
    let doc = Document::parse(&src);
    assert!(doc.is_lossless());
    let codes: Vec<&str> = doc.diagnostics().iter().map(|d| d.code).collect();
    for expect in [
        "SW001", "SW002", "SW004", "SW005", "SW006", "SW008", "SW009", "SW010",
    ] {
        assert!(
            codes.contains(&expect),
            "fixture should trigger {expect}, got {codes:?}"
        );
    }
}
