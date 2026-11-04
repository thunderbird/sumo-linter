/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! `docs/rules.md` must stay in step with `rules::RULES` (#50): one section per
//! code, no section for a code that does not exist, and each section's first
//! example must trigger its own rule.

use std::path::Path;
use sumo_wiki_core::{rules::RULES, Document, Product};

/// `(code, first fenced example)` for each `## SWnnn` section, in page order.
fn sections() -> Vec<(String, Option<String>)> {
    let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/rules.md");
    let page = std::fs::read_to_string(p).expect("docs/rules.md");
    let mut out: Vec<(String, Option<String>)> = Vec::new();
    let mut fence: Option<String> = None;
    for line in page.lines() {
        if let Some(buf) = fence.as_mut() {
            if line.starts_with("```") {
                let example = fence.take().unwrap();
                if let Some(last) = out.last_mut() {
                    last.1.get_or_insert(example);
                }
            } else {
                buf.push_str(line);
                buf.push('\n');
            }
        } else if line.starts_with("```") {
            fence = Some(String::new());
        } else if let Some(code) = line.strip_prefix("## SW") {
            out.push((format!("SW{}", code.trim()), None));
        }
    }
    out
}

#[test]
fn every_rule_has_one_section_and_no_more() {
    let documented: Vec<String> = sections().into_iter().map(|(c, _)| c).collect();
    let codes: Vec<String> = RULES.iter().map(|(c, _)| c.to_string()).collect();
    assert_eq!(documented, codes, "docs/rules.md sections vs rules::RULES");
}

#[test]
fn each_example_triggers_its_rule() {
    for (code, example) in sections() {
        let example = example.unwrap_or_else(|| panic!("{code} has no example"));
        // Thunderbird, as the web app and the editors lint, so SW012 fires.
        let got: Vec<&str> = Document::parse(&example)
            .diagnostics_for(Product::Thunderbird)
            .iter()
            .map(|d| d.code)
            .collect();
        assert!(
            got.contains(&code.as_str()),
            "{code}'s example gives {got:?}:\n{example}"
        );
    }
}
