/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! WASM bindings for the SUMO markup linter.
//!
//! Deliberately not using `wasm-bindgen`: the whole interface is one string in
//! and one JSON string out, which the bare `wasm32-unknown-unknown` ABI handles
//! with four exported functions. That means the browser build needs no npm, no
//! wasm-pack, and no toolchain beyond
//! `cargo build --release --target wasm32-unknown-unknown`.
//!
//! Calling convention, as used by `web/app.js`:
//!   1. `alloc(len)` → pointer to a `len`-byte buffer
//!   2. copy UTF-8 source into it
//!   3. `lint(ptr, len)` or `fix(ptr, len, unsafe_fixes)` → pointer to a
//!      NUL-terminated UTF-8 JSON result, owned by the module
//!   4. `dealloc(ptr, len)` to release the input buffer
//!
//! The result buffer is leaked deliberately and reclaimed on the next call, so
//! callers never have to free it.

use std::sync::Mutex;

use sumo_wiki_core::{line_col, Applicability, Document, HeadingSpacing, Style};

/// Holds the last result so its memory stays valid until the next call.
static LAST: Mutex<Option<std::ffi::CString>> = Mutex::new(None);

/// Allocate `len` bytes for the caller to write UTF-8 source into.
#[no_mangle]
pub extern "C" fn alloc(len: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(len);
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

/// Release a buffer previously returned by [`alloc`].
///
/// # Safety
/// `ptr` must be a pointer returned by [`alloc`] with the same `len`, not yet
/// freed. Passing anything else, or freeing twice, is undefined behaviour.
#[no_mangle]
pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
    if !ptr.is_null() && len > 0 {
        drop(Vec::from_raw_parts(ptr, 0, len));
    }
}

/// Lint UTF-8 source, returning a NUL-terminated JSON array of diagnostics.
///
/// # Safety
/// `ptr` must point to `len` initialised bytes.
#[no_mangle]
pub unsafe extern "C" fn lint(ptr: *const u8, len: usize) -> *const u8 {
    let src = read_input(ptr, len);
    let doc = Document::parse(src.clone());
    let rows: Vec<String> = doc
        .diagnostics()
        .iter()
        .map(|d| {
            let pos = line_col(&src, d.span.start);
            format!(
                r#"{{"line":{},"column":{},"start":{},"end":{},"code":"{}","severity":"{}","message":{},"fix":{}}}"#,
                pos.line,
                pos.col,
                d.span.start,
                d.span.end,
                d.code,
                d.severity.as_str(),
                json_str(&d.message),
                match d.fix.as_ref() {
                    Some(f) => format!(
                        r#"{{"safe":{},"description":{}}}"#,
                        f.applicability == Applicability::Safe,
                        json_str(&f.description)
                    ),
                    None => "null".to_string(),
                }
            )
        })
        .collect();
    hand_back(format!("[{}]", rows.join(",")))
}

/// Apply fixes and return `{"text":…,"applied":N}`.
///
/// # Safety
/// `ptr` must point to `len` initialised bytes.
#[no_mangle]
pub unsafe extern "C" fn fix(ptr: *const u8, len: usize, unsafe_fixes: u32) -> *const u8 {
    let src = read_input(ptr, len);
    let (out, n) = Document::parse(src).apply_fixes(unsafe_fixes != 0);
    hand_back(format!(r#"{{"text":{},"applied":{}}}"#, json_str(&out), n))
}

/// Apply phase-2 house style, returning `{"text":…,"changed":bool}`.
///
/// `heading_spacing`: 0 = preserve each article's own dominant style (default,
/// churn-avoiding), 1 = always spaced, 2 = always tight.
///
/// # Safety
/// `ptr` must point to `len` initialised bytes.
#[no_mangle]
pub unsafe extern "C" fn style(ptr: *const u8, len: usize, heading_spacing: u32) -> *const u8 {
    let src = read_input(ptr, len);
    let style = Style {
        heading_spacing: match heading_spacing {
            1 => HeadingSpacing::Spaced,
            2 => HeadingSpacing::Tight,
            _ => HeadingSpacing::PreserveDominant,
        },
        ..Style::thunderbird()
    };
    let out = Document::parse(src.clone()).format(&style);
    let changed = out != src;
    hand_back(format!(
        r#"{{"text":{},"changed":{}}}"#,
        json_str(&out),
        changed
    ))
}

/// Report whether the lexer round-trips this input. Exposed so the web app can
/// refuse to offer a "fix" button if the invariant the fixer depends on fails.
///
/// # Safety
/// `ptr` must point to `len` initialised bytes.
#[no_mangle]
pub unsafe extern "C" fn is_lossless(ptr: *const u8, len: usize) -> u32 {
    u32::from(Document::parse(read_input(ptr, len)).is_lossless())
}

unsafe fn read_input(ptr: *const u8, len: usize) -> String {
    if ptr.is_null() || len == 0 {
        return String::new();
    }
    String::from_utf8_lossy(std::slice::from_raw_parts(ptr, len)).into_owned()
}

/// Store `s` so it outlives the call, and return a pointer to its bytes.
fn hand_back(s: String) -> *const u8 {
    let c = std::ffi::CString::new(s).unwrap_or_default();
    let p = c.as_ptr() as *const u8;
    // Replacing the previous value frees it, so at most one result is retained.
    if let Ok(mut g) = LAST.lock() {
        *g = Some(c);
    }
    p
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

    /// Exercise the exact sequence the browser uses.
    #[test]
    fn lint_over_the_c_abi() {
        let src = "{for win}unclosed\n";
        let json = unsafe {
            let p = lint(src.as_ptr(), src.len());
            std::ffi::CStr::from_ptr(p as *const i8)
                .to_string_lossy()
                .into_owned()
        };
        assert!(json.contains("SW001"), "{json}");
        assert!(json.contains(r#""severity":"error""#), "{json}");
    }

    #[test]
    fn fix_over_the_c_abi() {
        // Mid-line, so `**` is unambiguously Markdown bold. At the start of a
        // line `**` is a nested list marker, which the next test pins down.
        let src = "see **bold** here\n";
        let json = unsafe {
            let p = fix(src.as_ptr(), src.len(), 0);
            std::ffi::CStr::from_ptr(p as *const i8)
                .to_string_lossy()
                .into_owned()
        };
        assert!(json.contains(r#""applied":1"#), "{json}");
        assert!(json.contains(r#"'''bold'''"#), "{json}");
    }

    /// `**item**` at the start of a line is a nested list item, not Markdown
    /// bold, so it must not be "fixed". Same family of mistake as trying to flag
    /// `# Text` as a Markdown heading when `#` is the ordered-list marker.
    #[test]
    fn double_asterisk_at_line_start_is_a_list_not_bold() {
        let src = "* outer\n** inner\n";
        let json = unsafe {
            let p = fix(src.as_ptr(), src.len(), 0);
            std::ffi::CStr::from_ptr(p as *const i8)
                .to_string_lossy()
                .into_owned()
        };
        assert!(json.contains(r#""applied":0"#), "{json}");
    }

    #[test]
    fn handles_empty_and_null_input() {
        unsafe {
            assert_eq!(is_lossless(std::ptr::null(), 0), 1);
            let p = lint(std::ptr::null(), 0);
            let s = std::ffi::CStr::from_ptr(p as *const i8)
                .to_string_lossy()
                .into_owned();
            assert_eq!(s, "[]");
        }
    }
}
