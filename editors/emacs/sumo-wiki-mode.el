;;; sumo-wiki-mode.el --- Major mode for SUMO Knowledge Base wiki markup -*- lexical-binding: t; -*-

;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at https://mozilla.org/MPL/2.0/.

;; Author: Thunderbird contributors
;; URL: https://github.com/thunderbird/sumo-linter
;; Version: 0.1.0
;; Package-Requires: ((emacs "27.1"))
;; Keywords: languages, wiki

;;; Commentary:

;; Editing support for the wiki markup used by support.mozilla.org Knowledge
;; Base articles.  This is Kitsune's own dialect, not Markdown.
;;
;; Linting comes from `sumo-lint-lsp', the same language server used by VS Code
;; and Neovim, so rules only exist in one place.  Two ways to hook it up:
;;
;;   Eglot (built in to Emacs 29+) -- registered automatically by this file.
;;   Just `M-x eglot' in a SUMO buffer.
;;
;;   lsp-mode -- also registered automatically when lsp-mode is loaded.
;;
;; If you would rather not run a language server, `sumo-wiki-flymake-setup'
;; drives the `sumo-lint' CLI through Flymake instead.  Both paths report the
;; same diagnostics.
;;
;; Build the tools first:
;;
;;   cargo build --release
;;   cp target/release/sumo-lint-lsp target/release/sumo-lint ~/.local/bin/
;;
;; SUMO itself remains the source of truth.  Files edited here are local drafts
;; that get pasted back into the article editor.

;;; Code:

(require 'flymake)
(require 'json)

(defgroup sumo-wiki nil
  "Editing support for SUMO Knowledge Base wiki markup."
  :group 'languages
  :prefix "sumo-wiki-")

(defcustom sumo-wiki-lsp-program "sumo-lint-lsp"
  "Executable for the SUMO markup language server."
  :type 'string
  :group 'sumo-wiki)

(defcustom sumo-wiki-cli-program "sumo-lint"
  "Executable for the SUMO markup command-line linter."
  :type 'string
  :group 'sumo-wiki)

;;; Faces

(defface sumo-wiki-macro-face
  '((t :inherit font-lock-builtin-face))
  "Face for inline macros such as `{key Ctrl+T}' and `{menu Settings}'."
  :group 'sumo-wiki)

(defface sumo-wiki-for-face
  '((t :inherit font-lock-keyword-face))
  "Face for `{for}' platform-conditional blocks."
  :group 'sumo-wiki)

(defface sumo-wiki-callout-face
  '((t :inherit font-lock-warning-face))
  "Face for `{note}' and `{warning}' callout delimiters."
  :group 'sumo-wiki)

(defface sumo-wiki-preformatted-face
  '((t :inherit font-lock-string-face :extend t))
  "Face for lines beginning with a space.

Such lines are rendered preformatted by the wiki, which is invisible in
source and easy to create by accident -- one stray leading space turns a
paragraph into a code block.  Highlighting the whole line makes that
visible while editing."
  :group 'sumo-wiki)

;;; Font lock

(defconst sumo-wiki-font-lock-keywords
  `(;; A leading space means preformatted.  First, so it wins over the inline
    ;; rules below: nothing inside such a line is interpreted as markup.
    ("^ +.*$" 0 'sumo-wiki-preformatted-face t)

    ;; Headings.  Both `= H =' and `=H=' are valid; neither is "correct".
    ("^\\(======\\)\\([^=\n]*\\)\\(======\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-function-name-face))
    ("^\\(=====\\)\\([^=\n]*\\)\\(=====\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-function-name-face))
    ("^\\(====\\)\\([^=\n]*\\)\\(====\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-function-name-face))
    ("^\\(===\\)\\([^=\n]*\\)\\(===\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-type-face))
    ("^\\(==\\)\\([^=\n]*\\)\\(==\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-type-face))
    ("^\\(=\\)\\([^=\n]*\\)\\(=\\)$"
     (1 font-lock-comment-delimiter-face) (2 font-lock-keyword-face))

    ;; Platform-conditional blocks: {for win,mac}, {for not mac}, {for =fx140}.
    ("{/?for\\(?: [^}\n]*\\)?}" 0 'sumo-wiki-for-face)

    ;; Callouts.
    ("{/?\\(?:note\\|warning\\)}" 0 'sumo-wiki-callout-face)

    ;; Inline macros.  The name is highlighted, the argument left as prose.
    ("\\({\\(?:key\\|button\\|menu\\|filepath\\|pref\\) \\)\\([^}\n]*\\)\\(}\\)"
     (1 'sumo-wiki-macro-face) (3 'sumo-wiki-macro-face))

    ;; Transclusions and templates before generic links, so their prefixes show.
    ("\\[\\[\\(?:Template\\|T\\|Include\\|I\\):[^]\n]*\\]\\]" 0 font-lock-preprocessor-face)
    ("\\[\\[\\(?:Image\\|Video\\|V\\|UI\\):[^]\n]*\\]\\]" 0 font-lock-constant-face)
    ;; Internal links: [[Page]] or [[Page|text]].
    ("\\[\\[[^]\n]*\\]\\]" 0 font-lock-string-face)
    ;; External links: [https://example.com label].
    ("\\[https?://[^]\n]*\\]" 0 font-lock-string-face)

    ;; Emphasis.  Five quotes is bold+italic, so it is matched first.
    ;; The face position in a font-lock rule is *evaluated*, so face names must
    ;; be quoted -- an unquoted `bold' is read as a variable and signals
    ;; void-variable on any buffer containing bold text.
    ("'''''\\(?:[^'\n]\\|'[^'\n]\\)*'''''" 0 '(:inherit bold :slant italic))
    ("'''\\(?:[^'\n]\\|'[^'\n]\\)*'''" 0 'bold)
    ("''\\(?:[^'\n]\\|'[^'\n]\\)*''" 0 'italic)

    ;; Structure.
    ("^[*#]+" 0 font-lock-builtin-face)
    ("^;" 0 font-lock-builtin-face)
    ("^----+$" 0 font-lock-comment-delimiter-face)
    ("__TOC__" 0 font-lock-preprocessor-face)

    ;; Table markup.
    ("^\\(?:{|\\||}\\||-\\||\\+\\)" 0 font-lock-builtin-face))
  "Font-lock rules for `sumo-wiki-mode'.")

;;; Syntax

(defvar sumo-wiki-mode-syntax-table
  (let ((table (make-syntax-table text-mode-syntax-table)))
    ;; Treat <!-- --> as comments so comment commands work.
    (modify-syntax-entry ?< "(> " table)
    (modify-syntax-entry ?> ")< " table)
    ;; Quotes are emphasis markers here, never string delimiters; leaving them
    ;; as string syntax makes every apostrophe in prose unbalance the buffer.
    (modify-syntax-entry ?' "." table)
    (modify-syntax-entry ?\" "." table)
    table)
  "Syntax table for `sumo-wiki-mode'.")

;;; Commands

(defun sumo-wiki--run-cli (args)
  "Pipe the current buffer through the linter with ARGS, returning its stdout.

The buffer's contents go to the program's stdin and stdout comes back as a
string.  Standard error is discarded: when acting as a filter the linter
sends diagnostics there, keeping stdout purely the transformed document.

Signals an error if the program is missing or exits unexpectedly."
  (unless (executable-find sumo-wiki-cli-program)
    (user-error "Cannot find `%s'; build it with `cargo build --release'"
                sumo-wiki-cli-program))
  (let ((out (generate-new-buffer " *sumo-lint-output*")))
    (unwind-protect
        (let ((exit (apply #'call-process-region
                           (point-min) (point-max)
                           sumo-wiki-cli-program
                           nil          ; do not delete the region
                           (list out nil) ; stdout to OUT, stderr discarded
                           nil          ; no redisplay
                           args)))
          ;; Exit code 1 only means "found errors", which is not a failure here.
          (unless (memq exit '(0 1))
            (error "%s exited with %s" sumo-wiki-cli-program exit))
          (with-current-buffer out (buffer-string)))
      (kill-buffer out))))

;;;###autoload
(defun sumo-wiki-fix-buffer ()
  "Apply safe fixes to the current buffer via `sumo-lint --fix'.

Only fixes marked safe are applied.  Repairs whose intent is a guess are
reported but left alone, because most markup errors have several plausible
corrections and choosing wrong silently changes what the article says."
  (interactive)
  (let ((fixed (sumo-wiki--run-cli '("--fix" "-")))
        (line (line-number-at-pos))
        (col (current-column)))
    (if (or (string-empty-p fixed) (string= fixed (buffer-string)))
        (message "sumo-lint: nothing to fix")
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert fixed))
      (goto-char (point-min))
      (forward-line (1- line))
      (move-to-column col)
      (message "sumo-lint: applied safe fixes"))))

;;;###autoload
(defun sumo-wiki-apply-style ()
  "Apply house style to the current buffer via `sumo-lint --style'.

By default headings are normalised to whichever style this article already
uses most, so an article that is internally consistent is left untouched.
That keeps cosmetic diffs off volunteer localizers' review queues."
  (interactive)
  (let ((styled (sumo-wiki--run-cli '("--style" "-")))
        (line (line-number-at-pos))
        (col (current-column)))
    (if (or (string-empty-p styled) (string= styled (buffer-string)))
        (message "sumo-lint: already consistent, nothing to change")
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert styled))
      (goto-char (point-min))
      (forward-line (1- line))
      (move-to-column col)
      (message "sumo-lint: house style applied"))))

;;; Flymake, for users who prefer not to run a language server

(defun sumo-wiki-flymake-backend (report-fn &rest _args)
  "Flymake backend running `sumo-lint' over the buffer, reporting to REPORT-FN."
  (let* ((source (current-buffer))
         (json (condition-case err
                   (sumo-wiki--run-cli '("--format" "json" "-"))
                 (error (funcall report-fn :panic :explanation (format "%s" err))
                        nil))))
    (when json
      (let* ((rows (condition-case nil
                       (json-parse-string json :object-type 'alist)
                     (error nil)))
             (diags
              (mapcar
               (lambda (row)
                 (let* ((line (alist-get 'line row))
                        (col (alist-get 'column row))
                        (msg (alist-get 'message row))
                        (code (alist-get 'code row))
                        (kind (if (equal (alist-get 'severity row) "error")
                                  :error :warning))
                        (region (flymake-diag-region source line col)))
                   (flymake-make-diagnostic
                    source (car region) (cdr region) kind
                    (format "[%s] %s" code msg))))
               (append rows nil))))
        (funcall report-fn diags)))))

;;;###autoload
(defun sumo-wiki-flymake-setup ()
  "Enable Flymake in this buffer using the `sumo-lint' CLI.
Use this instead of Eglot if you would rather not run a language server."
  (interactive)
  (add-hook 'flymake-diagnostic-functions #'sumo-wiki-flymake-backend nil t)
  (flymake-mode 1))

;;; Mode

(defvar sumo-wiki-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-f") #'sumo-wiki-fix-buffer)
    (define-key map (kbd "C-c C-s") #'sumo-wiki-apply-style)
    map)
  "Keymap for `sumo-wiki-mode'.")

;;;###autoload
(define-derived-mode sumo-wiki-mode text-mode "SUMO-Wiki"
  "Major mode for editing SUMO Knowledge Base wiki markup.

\\{sumo-wiki-mode-map}"
  :syntax-table sumo-wiki-mode-syntax-table
  (setq-local font-lock-defaults '(sumo-wiki-font-lock-keywords nil nil nil nil))
  (setq-local comment-start "<!-- ")
  (setq-local comment-end " -->")
  (setq-local comment-start-skip "<!--[ \t]*")
  ;; Wiki paragraphs are separated by blank lines; a line must not be reflowed
  ;; into its neighbour, since line breaks are meaningful in lists and tables.
  (setq-local paragraph-start "\\([ \t]*$\\|[*#;=]\\|{|\\)")
  (setq-local paragraph-separate "[ \t]*$")
  (setq-local require-final-newline t)
  ;; Tabs are flagged by the linter, so do not insert them.
  (setq-local indent-tabs-mode nil))

;;;###autoload
(add-to-list 'auto-mode-alist '("\\.sumo\\'" . sumo-wiki-mode))

;; `.wiki' is claimed by other wiki modes too, so it is registered but yields to
;; anything already handling it rather than overriding a user's existing setup.
;;;###autoload
(add-to-list 'auto-mode-alist '("\\.wiki\\'" . sumo-wiki-mode) t)

;;; Language server integration

;; Declared rather than required: eglot is only loaded if the user uses it, but
;; the byte-compiler still wants to know the variable exists.
(defvar eglot-server-programs)

;; Eglot ships with Emacs 29+.  Registering inside `with-eval-after-load' means
;; users need no configuration beyond `M-x eglot'.
(with-eval-after-load 'eglot
  (add-to-list 'eglot-server-programs
               `(sumo-wiki-mode . (,sumo-wiki-lsp-program))))

(with-eval-after-load 'lsp-mode
  (with-no-warnings
    (add-to-list 'lsp-language-id-configuration '(sumo-wiki-mode . "sumo-wiki"))
    (lsp-register-client
     (make-lsp-client
      :new-connection (lsp-stdio-connection (lambda () sumo-wiki-lsp-program))
      :major-modes '(sumo-wiki-mode)
      :server-id 'sumo-lint))))

(provide 'sumo-wiki-mode)
;;; sumo-wiki-mode.el ends here
