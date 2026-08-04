/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

//! Diagnostics and machine-applicable fixes.

use core::ops::Range;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    /// Markup that renders wrongly or breaks structure.
    Error,
    /// Suspicious but possibly deliberate.
    Warning,
}

impl Severity {
    pub fn as_str(self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
        }
    }
}

/// How confident we are that applying a fix preserves author intent.
///
/// Only `Safe` fixes are applied without an explicit opt-in. This distinction is
/// load-bearing: most phase-1 errors (an unbalanced `'''`, for instance) have
/// several plausible repairs, and guessing wrong silently corrupts an article.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Applicability {
    Safe,
    Unsafe,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Fix {
    pub span: Range<usize>,
    pub replacement: String,
    pub applicability: Applicability,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Diagnostic {
    /// Stable rule code, e.g. `SW001`. Stable across versions so it can be
    /// referenced in review comments and suppressed by name.
    pub code: &'static str,
    pub severity: Severity,
    pub message: String,
    pub span: Range<usize>,
    pub fix: Option<Fix>,
}

impl Diagnostic {
    pub fn new(
        code: &'static str,
        severity: Severity,
        message: impl Into<String>,
        span: Range<usize>,
    ) -> Self {
        Self {
            code,
            severity,
            message: message.into(),
            span,
            fix: None,
        }
    }

    pub fn with_fix(mut self, fix: Fix) -> Self {
        self.fix = Some(fix);
        self
    }
}

/// 1-based line and column (column counted in characters, not bytes).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LineCol {
    pub line: usize,
    pub col: usize,
}

/// Convert a byte offset to a 1-based line/column position.
pub fn line_col(input: &str, offset: usize) -> LineCol {
    let upto = &input[..offset.min(input.len())];
    let line = upto.bytes().filter(|c| *c == b'\n').count() + 1;
    let col = upto.rsplit('\n').next().unwrap_or("").chars().count() + 1;
    LineCol { line, col }
}
