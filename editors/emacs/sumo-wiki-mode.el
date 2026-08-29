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

(defcustom sumo-wiki-paste-url-as-link t
  "Whether yanking a URL over an active region writes a link.

With this on, selecting some words and yanking a URL gives
`[https://example.org the words]' instead of replacing the selection.
Set to nil to make yanking always yank."
  :type 'boolean
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

(defun sumo-wiki--url-p (string)
  "Return non-nil when STRING carries a URL scheme SUMO links externally."
  (string-match-p "\\`\\(?:https?\\|ftp\\|mailto\\):" (downcase string)))

(defun sumo-wiki--link-from-paste (pasted selected)
  "Return the link markup for yanking PASTED over SELECTED, or nil.

nil means \"just yank\", and every case that is not unambiguously
select-words-then-yank-a-URL returns it: a yank handler that guesses is
worse than no yank handler, because what it silently mangles is whatever
was on the clipboard.  Kept as a pure function of two strings so the
tests need no buffer."
  (let ((url (string-trim (or pasted "")))
        (text (string-trim (or selected ""))))
    (when (and
           ;; A URL never contains whitespace, so anything that does is prose
           ;; that merely starts with a scheme, and yanking it is a replace.
           (sumo-wiki--url-p url)
           (not (string-match-p "[ \t\n]" url))
           ;; Nothing selected means no link text, so this is an ordinary yank.
           (not (string-empty-p text))
           ;; Replacing one URL with another is a correction, not a link.
           (not (sumo-wiki--url-p text))
           ;; A multi-line region has no sensible label, and brackets would
           ;; close the link early.  `|' is safe: it only separates in [[...]].
           (not (string-match-p "[]\n[]" text)))
      (format "[%s %s]" url text))))

(defun sumo-wiki--kill-text ()
  "Return the head of the kill ring without rotating it, or nil if empty."
  (condition-case nil
      (current-kill 0 t)
    (error nil)))

;;;###autoload
(defun sumo-wiki-yank (&optional arg)
  "Yank, or write a link when yanking a URL over an active region.

Select some words, copy a URL, yank: you get `[url the words]' rather
than the selection replaced.  This is the same gesture VS Code and
Markdown mode use, and it is usually the faster of the two ways to write
a link, since the clipboard already holds the URL.

Everything else yanks exactly as before, with ARG passed through, so
this stays safe on whatever `yank' is bound to.  Only the external form
is produced: an internal link goes by article *title*, which a
`/kb/<slug>' URL does not carry."
  (interactive "*P")
  (let ((link (and sumo-wiki-paste-url-as-link
                   (use-region-p)
                   (sumo-wiki--link-from-paste
                    (sumo-wiki--kill-text)
                    (buffer-substring-no-properties
                     (region-beginning) (region-end))))))
    (if (not link)
        (yank arg)
      (delete-region (region-beginning) (region-end))
      (insert link))))

;; `delete-selection-mode' deletes the region in `pre-command-hook', which would
;; leave `sumo-wiki-yank' with nothing to use as link text.  A function-valued
;; property is the supported way to say "not this time": nil suppresses the
;; deletion, `yank' asks for the ordinary behaviour.
(defun sumo-wiki--yank-delete-selection ()
  "Tell `delete-selection-mode' whether to delete the region before a yank."
  (if (and sumo-wiki-paste-url-as-link
           (use-region-p)
           (sumo-wiki--link-from-paste
            (sumo-wiki--kill-text)
            (buffer-substring-no-properties (region-beginning) (region-end))))
      nil
    'yank))

(put 'sumo-wiki-yank 'delete-selection #'sumo-wiki--yank-delete-selection)

(defun sumo-wiki--build-link (target label)
  "Return SUMO markup linking to TARGET with link text LABEL.

Anything with a scheme is external and takes a space; anything else is an
internal link by article *title* -- not slug -- and takes a pipe.  LABEL
may be empty, which is meaningful for both forms: `[[Article title]]'
renders the title and a bare `[url]' renders the URL."
  (let ((t* (string-trim (or target "")))
        (l (string-trim (or label ""))))
    (if (sumo-wiki--url-p t*)
        (if (string-empty-p l) (format "[%s]" t*) (format "[%s %s]" t* l))
      ;; A label identical to the title adds nothing but localizer diff noise.
      (if (or (string-empty-p l) (equal l t*))
          (format "[[%s]]" t*)
        (format "[[%s|%s]]" t* l)))))

(defun sumo-wiki--validate-target (target)
  "Return a complaint about TARGET, or nil when it is usable."
  (let ((t* (string-trim target)))
    (cond
     ((string-empty-p t*)
      "Enter a URL, an article title, or a #w_anchor on this page.")
     ((string-match-p "[][]" t*) "A link target cannot contain [ or ].")
     ;; In `[[Title|text]]' the pipe is the separator, so one here would split
     ;; the target.
     ((string-match-p "|" t*)
      "A link target cannot contain | -- that separates the target from the text.")
     (t nil))))

(defun sumo-wiki--validate-label (label target)
  "Return a complaint about LABEL for TARGET, or nil when it is usable."
  (let ((l (string-trim label)))
    (cond
     ((string-match-p "[][]" l) "Link text cannot contain [ or ].")
     ;; External links have no pipe syntax, so there it is just a character.
     ((and (string-match-p "|" l) (not (sumo-wiki--url-p (string-trim target))))
      "Link text cannot contain | in an internal link.")
     (t nil))))

(defun sumo-wiki--seed-from-selection (selection)
  "Split SELECTION into a starting (TARGET . LABEL) for the prompts.

So the common cases -- mark a URL, or mark the words you want linked --
need only one thing typed.  Marked markup seeds nothing: it would seed
unusable values, and rewriting an existing link is SW009's quick fix,
which knows the span."
  (let ((s (string-trim (or selection ""))))
    (cond
     ((or (string-empty-p s) (string-match-p "[]\n[|]" s)) (cons "" ""))
     ((sumo-wiki--url-p s) (cons s ""))
     (t (cons "" s)))))

(defun sumo-wiki--read-validated (prompt initial validate)
  "Read a string with PROMPT and INITIAL, re-asking until VALIDATE passes.

VALIDATE follows the same contract as VS Code's `validateInput': a string
is the complaint, nil means accepted.  `C-g' aborts the whole command,
which is the counterpart of dismissing the input box."
  (let ((value nil) (complaint nil))
    (while (progn
             (setq value (read-string (if complaint
                                          (concat complaint "  " prompt)
                                        prompt)
                                      initial))
             (setq complaint (funcall validate value))))
    value))

;;;###autoload
(defun sumo-wiki-insert-link ()
  "Insert a link, asking for the target and the link text.

The counterpart of `SUMO: Insert Link' in VS Code, and the other half of
`sumo-wiki-yank': use this one when there is nothing on the clipboard
to paste, and it is the only way to write an internal `[[Title|text]]'
link, since an article title cannot be derived from a URL.

The region, if any, seeds the prompts and is replaced."
  (interactive "*")
  (let* ((seed (sumo-wiki--seed-from-selection
                (and (use-region-p)
                     (buffer-substring-no-properties
                      (region-beginning) (region-end)))))
         (target (sumo-wiki--read-validated
                  "Link target (URL, article title, or #w_anchor): "
                  (car seed) #'sumo-wiki--validate-target))
         (label (sumo-wiki--read-validated
                 (if (sumo-wiki--url-p (string-trim target))
                     "Link text (empty shows the URL itself): "
                   "Link text (empty shows the article title): ")
                 (cdr seed)
                 (lambda (value) (sumo-wiki--validate-label value target)))))
    (when (use-region-p)
      (delete-region (region-beginning) (region-end)))
    (insert (sumo-wiki--build-link target label))))

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
    (define-key map (kbd "C-c C-l") #'sumo-wiki-insert-link)
    ;; A remap rather than a key, so this follows `yank' wherever it is bound —
    ;; `C-y', and `s-v' on macOS — instead of guessing at one of them.
    (define-key map [remap yank] #'sumo-wiki-yank)
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
