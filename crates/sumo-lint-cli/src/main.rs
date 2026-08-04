/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! `sumo-lint` — command-line linter for SUMO Knowledge Base wiki markup.
//!
//! Argument parsing is hand-rolled rather than using clap. The surface is small,
//! and keeping the whole workspace dependency-free means fast builds, a trivial
//! audit surface, and nothing that might not compile to WASM later.

use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use sumo_wiki_core::{
    line_col, rules::RULES, Applicability, Document, HeadingSpacing, Severity, Style,
};

const USAGE: &str = "\
sumo-lint — lint SUMO Knowledge Base wiki markup

USAGE:
    sumo-lint [OPTIONS] <PATH>...     files, or directories of *.wiki / *.sumo
    sumo-lint -                       read from stdin

OPTIONS:
    --fix                apply safe fixes in place (phase 1: errors)
    --unsafe-fixes       also apply fixes whose intent is a guess (implies --fix)
    --style              apply house-style formatting in place (phase 2)
    --diff               show what --fix / --style would change, without writing

STYLE OPTIONS:
    --heading-spacing <preserve|spaced|tight>
                         preserve (default) normalises each article to whichever
                         style it already uses most, leaving already-consistent
                         articles byte-identical. Use spaced or tight only once a
                         convention has been agreed.
    --strip-trailing-whitespace
                         also remove trailing spaces and tabs. Off by default: it
                         changes 64% of articles instead of 15%, with no rendered
                         difference, and every diff is reviewed by a localizer.
    --format <text|json> output format (default: text)
    --quiet              only print the summary
    --list-rules         list every rule and exit
    -h, --help           print this help

EXIT CODES:
    0  no errors
    1  at least one error-level diagnostic
    2  bad usage, or a file could not be read

Warnings do not affect the exit code; only errors do.
";

#[derive(Default)]
struct Opts {
    fix: bool,
    style: bool,
    unsafe_fixes: bool,
    diff: bool,
    json: bool,
    quiet: bool,
    paths: Vec<PathBuf>,
    stdin: bool,
    heading_spacing: HeadingSpacing,
    strip_trailing_whitespace: bool,
}

fn main() -> ExitCode {
    let mut o = Opts::default();
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "-h" | "--help" => {
                print!("{USAGE}");
                return ExitCode::SUCCESS;
            }
            "--list-rules" => {
                for (code, desc) in RULES {
                    println!("{code}  {desc}");
                }
                return ExitCode::SUCCESS;
            }
            "--fix" => o.fix = true,
            "--style" => o.style = true,
            "--strip-trailing-whitespace" => o.strip_trailing_whitespace = true,
            "--heading-spacing" => match args.next().as_deref() {
                Some("preserve") => o.heading_spacing = HeadingSpacing::PreserveDominant,
                Some("spaced") => o.heading_spacing = HeadingSpacing::Spaced,
                Some("tight") => o.heading_spacing = HeadingSpacing::Tight,
                other => {
                    eprintln!(
                        "error: --heading-spacing expects preserve|spaced|tight, got {other:?}"
                    );
                    return ExitCode::from(2);
                }
            },
            "--unsafe-fixes" => {
                o.fix = true;
                o.unsafe_fixes = true;
            }
            "--diff" => o.diff = true,
            "--quiet" => o.quiet = true,
            "--format" => match args.next().as_deref() {
                Some("json") => o.json = true,
                Some("text") => {}
                other => {
                    eprintln!("error: --format expects `text` or `json`, got {other:?}");
                    return ExitCode::from(2);
                }
            },
            "-" => o.stdin = true,
            s if s.starts_with('-') => {
                eprintln!("error: unknown option `{s}`\n\n{USAGE}");
                return ExitCode::from(2);
            }
            s => o.paths.push(PathBuf::from(s)),
        }
    }

    if o.paths.is_empty() && !o.stdin {
        eprint!("{USAGE}");
        return ExitCode::from(2);
    }

    let mut inputs: Vec<(String, String)> = Vec::new();
    if o.stdin {
        let mut buf = String::new();
        if let Err(e) = std::io::stdin().read_to_string(&mut buf) {
            eprintln!("error: reading stdin: {e}");
            return ExitCode::from(2);
        }
        inputs.push(("<stdin>".into(), buf));
    }
    for p in &o.paths {
        for f in expand(p) {
            match std::fs::read_to_string(&f) {
                Ok(s) => inputs.push((f.display().to_string(), s)),
                Err(e) => {
                    eprintln!("error: {}: {e}", f.display());
                    return ExitCode::from(2);
                }
            }
        }
    }

    let mut errors = 0usize;
    let mut warnings = 0usize;
    let mut fixed_files = 0usize;
    let mut json_rows: Vec<String> = Vec::new();

    // When reading stdin and rewriting, stdout carries the *document* and
    // nothing else, so the tool can be used as a filter:
    //
    //     sumo-lint --fix - < draft.wiki > fixed.wiki
    //
    // Editor integrations depend on this. Emacs, Vim/ALE and git hooks all pipe
    // a buffer through and read the result back; interleaving diagnostics with
    // the document on stdout silently corrupts the buffer.
    let filtering = o.stdin && (o.fix || o.style) && !o.diff;
    let emit = |s: String| {
        if filtering {
            eprintln!("{s}");
        } else {
            println!("{s}");
        }
    };

    for (name, src) in &inputs {
        let doc = Document::parse(src.clone());

        // A lexer bug would silently corrupt files under --fix, so refuse to go
        // any further if the round-trip property does not hold for this input.
        if !doc.is_lossless() {
            eprintln!(
                "internal error: {name}: lexer is not lossless for this file; refusing to continue"
            );
            return ExitCode::from(2);
        }

        for d in doc.diagnostics() {
            match d.severity {
                Severity::Error => errors += 1,
                Severity::Warning => warnings += 1,
            }
            let pos = line_col(src, d.span.start);
            if o.json {
                json_rows.push(format!(
                    r#"{{"file":{},"line":{},"column":{},"code":"{}","severity":"{}","message":{},"fixable":{}}}"#,
                    jstr(name),
                    pos.line,
                    pos.col,
                    d.code,
                    d.severity.as_str(),
                    jstr(&d.message),
                    d.fix.as_ref().is_some_and(|f| f.applicability == Applicability::Safe)
                ));
            } else if !o.quiet {
                emit(format!(
                    "{name}:{}:{}: {} [{}] {}",
                    pos.line,
                    pos.col,
                    d.severity.as_str(),
                    d.code,
                    d.message
                ));
                if let Some(f) = &d.fix {
                    let tag = match f.applicability {
                        Applicability::Safe => "fix",
                        Applicability::Unsafe => "fix (unsafe)",
                    };
                    emit(format!("    {tag}: {}", f.description));
                }
            }
        }

        if o.fix || o.style || o.diff {
            // Fixes repair errors; style expresses a convention. Both are applied
            // through the same write path so a file is only rewritten once.
            let (mut out, n) = if o.fix || o.diff {
                doc.apply_fixes(o.unsafe_fixes)
            } else {
                (src.clone(), 0)
            };
            if o.style {
                let style = Style {
                    heading_spacing: o.heading_spacing,
                    trailing_whitespace: o.strip_trailing_whitespace,
                };
                out = Document::parse(out).format(&style);
            }
            if out != *src {
                if o.diff {
                    println!("--- {name}\n+++ {name} (fixed)");
                    print_diff(src, &out);
                } else if name == "<stdin>" {
                    let _ = std::io::stdout().write_all(out.as_bytes());
                } else {
                    if let Err(e) = std::fs::write(name, &out) {
                        eprintln!("error: writing {name}: {e}");
                        return ExitCode::from(2);
                    }
                    fixed_files += 1;
                    let what = if o.style && n > 0 {
                        format!("{n} fix{} and style changes", plural(n))
                    } else if o.style {
                        "style changes".to_string()
                    } else {
                        format!("{n} fix{}", plural(n))
                    };
                    println!("{name}: applied {what}");
                }
            }
        }
    }

    if o.json {
        emit(format!("[{}]", json_rows.join(",")));
    } else {
        emit(format!(
            "checked {} file{}: {errors} error{}, {warnings} warning{}{}",
            inputs.len(),
            plural(inputs.len()),
            plural(errors),
            plural(warnings),
            if fixed_files > 0 {
                format!(", {fixed_files} file{} fixed", plural(fixed_files))
            } else {
                String::new()
            }
        ));
    }

    if errors > 0 {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}

fn plural(n: usize) -> &'static str {
    if n == 1 {
        ""
    } else {
        "s"
    }
}

/// Expand a directory into the `.wiki` / `.sumo` files it contains, recursively.
fn expand(p: &Path) -> Vec<PathBuf> {
    if p.is_file() {
        return vec![p.to_path_buf()];
    }
    let Ok(rd) = std::fs::read_dir(p) else {
        return vec![p.to_path_buf()];
    };
    let mut entries: Vec<PathBuf> = rd.filter_map(Result::ok).map(|e| e.path()).collect();
    entries.sort();
    let mut out = Vec::new();
    for e in entries {
        if e.is_dir() {
            out.extend(expand(&e));
        } else if e.extension().is_some_and(|x| x == "wiki" || x == "sumo") {
            out.push(e);
        }
    }
    out
}

/// Minimal line diff: enough to review a fix, not a general-purpose differ.
fn print_diff(before: &str, after: &str) {
    let (a, b): (Vec<&str>, Vec<&str>) = (before.lines().collect(), after.lines().collect());
    let (mut i, mut j) = (0usize, 0usize);
    while i < a.len() || j < b.len() {
        match (a.get(i), b.get(j)) {
            (Some(x), Some(y)) if x == y => {
                i += 1;
                j += 1;
            }
            (Some(x), Some(y)) => {
                println!("-{x}");
                println!("+{y}");
                i += 1;
                j += 1;
            }
            (Some(x), None) => {
                println!("-{x}");
                i += 1;
            }
            (None, Some(y)) => {
                println!("+{y}");
                j += 1;
            }
            (None, None) => break,
        }
    }
}

/// JSON string escaping, hand-rolled to keep the dependency count at zero.
fn jstr(s: &str) -> String {
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
