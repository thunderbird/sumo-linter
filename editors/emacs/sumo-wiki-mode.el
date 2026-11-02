;;; sumo-wiki-mode.el --- Major mode for SUMO Knowledge Base wiki markup -*- lexical-binding: t; -*-

;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at https://mozilla.org/MPL/2.0/.

;; Author: Thunderbird contributors
;; URL: https://github.com/thunderbird/sumo-linter
;; Version: 0.2.0
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

(require 'cl-lib)
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

;; One face per color class of SUMO's own editor (sumo-linter #37), with
;; SUMO's colors from Kitsune's config/themes/_light.scss and _dark.scss.
;; Customize any of them to suit a theme.

(defface sumo-wiki-syntax-face
  '((((background dark)) :foreground "#E9A1A1")
    (t :foreground "#D98484"))
  "Face for markup delimiters and names.
For example `''''', `{menu', `}', `__TOC__' and list markers."
  :group 'sumo-wiki)

(defface sumo-wiki-link-face
  '((((background dark)) :foreground "#8FBEFA" :underline t)
    (t :foreground "#5757C2" :underline t))
  "Face for links, `[[...]]' and `[...]', brackets included."
  :group 'sumo-wiki)

(defface sumo-wiki-bold-face
  '((((background dark)) :foreground "#F9F9FB")
    (t :foreground "#000000"))
  "Face for bold text and heading lines.

SUMO shows them in a stronger color, not in bold, so that the columns
of a monospace font stay aligned."
  :group 'sumo-wiki)

(defface sumo-wiki-italic-face
  '((t :slant italic))
  "Face for italic text, macro arguments and `{for}' conditions."
  :group 'sumo-wiki)

(defface sumo-wiki-comment-face
  '((((background dark)) :foreground "#83D5AD")
    (t :foreground "#009900"))
  "Face for `<!-- -->' comments and `<nowiki>', `<code>', `<pre>' content."
  :group 'sumo-wiki)

(defface sumo-wiki-quote-face
  '((((background dark)) :foreground "#F9F9FB" :background "#3A3D43")
    (t :foreground "#FFFFFF" :background "#000000"))
  "Face for lines beginning with a space.

Such lines are rendered preformatted by the wiki, which is invisible in
source and easy to create by accident -- one stray leading space turns a
paragraph into a code block."
  :group 'sumo-wiki)

(defface sumo-wiki-underline-face
  '((t :underline t))
  "Face for `<u>' text."
  :group 'sumo-wiki)

(defface sumo-wiki-strikethrough-face
  '((t :strike-through t))
  "Face for `<s>' and `<del>' text."
  :group 'sumo-wiki)

;; The faces before sumo-linter #37.
(define-obsolete-face-alias 'sumo-wiki-macro-face 'sumo-wiki-syntax-face "0.2.0")
(define-obsolete-face-alias 'sumo-wiki-for-face 'sumo-wiki-syntax-face "0.2.0")
(define-obsolete-face-alias 'sumo-wiki-callout-face 'sumo-wiki-syntax-face "0.2.0")
(define-obsolete-face-alias 'sumo-wiki-preformatted-face 'sumo-wiki-quote-face "0.2.0")

;;; Font lock

;; SUMO does not highlight with its wiki parser.  Its editor is CodeMirror 5
;; with a "simple mode": for each state, regular expressions that are tried in
;; order at the current position.  The first that matches gives the colors and
;; perhaps a new state; if none matches, CodeMirror moves one character on.
;; The state carries across lines, for example inside `<!-- -->'.
;;
;; The rules below are those of Kitsune's codemirror.sumo-mode.js at commit
;; 908a9601bb628d69aed824bfed68928f2f8983ac, Copyright (c) 2011, 2012, 2013
;; Mozilla Foundation, BSD-3-Clause (web/highlight.js holds the full notice),
;; translated to Emacs regexps.  Plain font-lock keywords cannot do this:
;; a later keyword colors text inside an earlier match.  So one matcher runs
;; the rules line by line, and the state at the end of each line is kept on
;; its newline, as `syntax-ppss' keeps its cache.
;;
;; editors/highlight-check.mjs compares the result with web/highlight.js over
;; every committed article, so keep the rules in Kitsune's order.

(defconst sumo-wiki--space
  "\t\v\f\r    -     　﻿"
  "The characters of JavaScript's `\\s', less the newline.")

(defconst sumo-wiki--for-condition
  (concat "\\(?:\\(?:,[" sumo-wiki--space "]?\\)?\\(?:not[" sumo-wiki--space "]\\)?"
          "\\(?:\\(?:win\\(?:xp\\|7\\|8\\|10\\|11\\)?\\|mac\\|linux\\|android\\|maemo\\)"
          "\\|=?\\(?:fx\\|tb\\|m\\|ios\\)[0-9]*\\)\\)+")
  "A `{for}' condition, as in SUMO's rules.")

(defconst sumo-wiki--rules
  (let ((ws (concat "[" sumo-wiki--space "]"))
        (non-ws (concat "[^" sumo-wiki--space "\n]"))
        (s 'sumo-wiki-syntax-face)
        (l 'sumo-wiki-link-face))
    ;; Each rule: (REGEXP FACES NEXT-STATE START-OF-LINE-ONLY).  FACES is one
    ;; face for the whole match, or a list with one face per group.
    `((start
       ("__TOC__" ,s)
       ("\\({\\)\\(for\\)" (,s ,s) for)
       ("\\({\\)\\(note\\|warning\\)" (,s ,s) close)
       ("{/\\(?:for\\|note\\|warning\\)}" ,s)
       ("</?br>" ,s)
       ("\\({\\)\\(filepath\\|key\\|menu\\|button\\|pref\\)\\(.*?\\)\\(}\\)"
        (,s ,s sumo-wiki-italic-face ,s))
       ("\\[\\[[^]]*?|.*?]]" ,l)
       (,(concat "\\[\\[" non-ws "*:.*?]]") ,l)
       ("\\[\\[.*?]]" ,l)
       (,(concat "\\[" non-ws "*.*?]") ,l)
       ("\\('''\\)\\(.*?\\)\\('''\\)" (,s sumo-wiki-bold-face ,s))
       ("\\(''\\)\\(.*?\\)\\(''\\)" (,s sumo-wiki-italic-face ,s))
       ("\\(<u>\\)\\(.*?\\)\\(</u>\\)" (,s sumo-wiki-underline-face ,s))
       ("\\(<s>\\)\\(.*?\\)\\(</s>\\)" (,s sumo-wiki-strikethrough-face ,s))
       ("\\(<del>\\)\\(.*?\\)\\(</del>\\)" (,s sumo-wiki-strikethrough-face ,s))
       ("<nowiki>" ,s nowiki)
       ("<code>" ,s code)
       ("<pre>" ,s pre)
       (,(concat ws "+.*") sumo-wiki-quote-face nil t)
       ("\\(=\\{1,6\\}\\)\\(.*?\\)\\1$" sumo-wiki-bold-face nil t)
       ("-\\{4\\}" ,s nil t)
       ("[;:#*]+" ,s nil t)
       ("{?[|!][-+]?}?" ,s nil t)
       ("<!--" sumo-wiki-comment-face comment))
      (comment
       (".*?-->" sumo-wiki-comment-face start)
       (".+" sumo-wiki-comment-face))
      ;; SUMO's rule is `.', one character at a time; a run up to the next
      ;; `<' gives the same colors faster.
      (nowiki ("</nowiki>" ,s start) ("[^<]+\\|." sumo-wiki-comment-face))
      (code ("</code>" ,s start) ("[^<]+\\|." sumo-wiki-comment-face))
      (pre ("</pre>" ,s start) ("[^<]+\\|." sumo-wiki-comment-face))
      (for
       (,sumo-wiki--for-condition sumo-wiki-italic-face close)
       ("{/for}" ,s))
      (close ("}" ,s start))))
  "SUMO's highlighting rules, per state.")

(defconst sumo-wiki--skip
  '((start . "^_{<['") (for . "^,nwmlaf=ti{") (close . "^}"))
  "Per state, the characters that cannot start a rule except at a line start.
Skipping them is only an optimization: no rule can match there.")

(defvar-local sumo-wiki--state-valid 1
  "The states kept on newlines before this position are up to date.")

(defun sumo-wiki--paint (faces)
  "Put FACES on the last match: one face, or one per group."
  (if (symbolp faces)
      (put-text-property (match-beginning 0) (match-end 0) 'face faces)
    (let ((i 1))
      (dolist (face faces)
        (when (and (match-beginning i) (< (match-beginning i) (match-end i)))
          (put-text-property (match-beginning i) (match-end i) 'face face))
        (setq i (1+ i))))))

(defun sumo-wiki--line (state paint)
  "Run the rules over the line at point, starting in STATE.
Point must be at the start of a line.  Put faces when PAINT is non-nil.
Move to the start of the next line, keep the state there, and return it."
  (let ((bol (point))
        (eol (line-end-position))
        (case-fold-search nil))
    (save-restriction
      (narrow-to-region bol eol)
      (while (< (point) eol)
        (let ((rules (alist-get state sumo-wiki--rules))
              (matched nil))
          (while (and rules (not matched))
            (let ((rule (car rules)))
              (when (and (or (not (nth 3 rule)) (= (point) bol))
                         (looking-at (car rule))
                         (< (point) (match-end 0)))
                (setq matched t)
                (when paint (sumo-wiki--paint (nth 1 rule)))
                (when (nth 2 rule) (setq state (nth 2 rule)))
                (goto-char (match-end 0))))
            (setq rules (cdr rules)))
          (unless matched
            (forward-char 1)
            (let ((skip (alist-get state sumo-wiki--skip)))
              (when skip (skip-chars-forward skip eol)))))))
    (when (< eol (point-max))
      (with-silent-modifications
        (put-text-property eol (1+ eol) 'sumo-wiki-state state))
      (when (<= bol sumo-wiki--state-valid)
        (setq sumo-wiki--state-valid (max sumo-wiki--state-valid (1+ eol)))))
    (goto-char (min (1+ eol) (point-max)))
    state))

(defun sumo-wiki--state-at (bol)
  "The state at BOL, the start of a line, running the rules from the last
known state if needed."
  (save-excursion
    (goto-char (min bol sumo-wiki--state-valid (point-max)))
    (beginning-of-line)
    (let ((state (if (bobp) 'start (get-text-property (1- (point)) 'sumo-wiki-state))))
      (unless state
        (goto-char (point-min))
        (setq state 'start))
      (while (< (point) bol)
        (setq state (sumo-wiki--line state nil)))
      state)))

(defun sumo-wiki--fontify (limit)
  "Font-lock matcher: highlight from point to LIMIT with SUMO's rules.
It puts the faces itself, so it always returns nil."
  (beginning-of-line)
  (let ((state (sumo-wiki--state-at (point))))
    (while (< (point) limit)
      (setq state (sumo-wiki--line state t))))
  nil)

(defun sumo-wiki--after-change (beg _end _len)
  "Forget the states from the line of BEG on."
  (setq sumo-wiki--state-valid
        (min sumo-wiki--state-valid
             (save-excursion (goto-char beg) (line-beginning-position)))))

(defconst sumo-wiki-font-lock-keywords
  '((sumo-wiki--fontify))
  "Font-lock rules for `sumo-wiki-mode': one matcher that runs SUMO's rules.")

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

;;; Bold
;;
;; SUMO bold is `'''three quotes''', which is six characters to type by hand
;; and easy to leave unbalanced (SW003).  The same rules live in `bold.js'
;; (VS Code) and `sumo_wiki#toggle_bold' (Vim).

(defconst sumo-wiki--bold-mark "'''"
  "The marker SUMO uses for bold text.  Not `**'; that is what SW010 flags.")

(defun sumo-wiki--count-bold-marks (text)
  "Return how many bold markers TEXT contains, counted without overlap.

So `'''''' -- bold plus italic -- counts as the one bold marker it is."
  (let ((n 0) (i 0))
    (while (string-match sumo-wiki--bold-mark text i)
      (setq n (1+ n) i (match-end 0)))
    n))

(defun sumo-wiki--toggle-bold (before selected after)
  "Return the edit that toggles bold over SELECTED, or nil to refuse.

BEFORE and AFTER are the rest of the line on either side: `''' does not
span lines, so one line is all the context there is.

nil means \"do nothing and say so\".  A toggle that guesses turns markup
into a run of quotes that renders as something else entirely.

On success the value is a plist: replace the region from CUT-BEFORE
characters before SELECTED to CUT-AFTER characters after it with TEXT,
then mark SEL-START to SEL-END, counted from the start of TEXT.  Leaving
the inner text marked is what makes a second press undo the first."
  (let* ((sel (or selected ""))
         (head (or before ""))
         (tail (or after ""))
         (mark sumo-wiki--bold-mark)
         (width (length mark)))
    (unless (string-match-p "\n" sel)
      (let* ((len (length sel))
             (lead-end (if (string-match "\\`[ \t]+" sel) (match-end 0) 0))
             (trail-start (if (string-match "[ \t]+\\'" sel)
                              (match-beginning 0) len))
             ;; A region of nothing but whitespace has no core to wrap, and the
             ;; two matches above overlap on it.
             (blank (<= trail-start lead-end))
             ;; Outer whitespace stays outside the markers: `''' x ''' renders
             ;; the spaces inside the bold run, which is never what marking a
             ;; word and a trailing space meant.
             (lead (if blank sel (substring sel 0 lead-end)))
             (core (if blank "" (substring sel lead-end trail-start)))
             (trail (if blank "" (substring sel trail-start))))
        (cond
         ;; The region is exactly a bold span: take the markers off.  Five
         ;; quotes is bold+italic, so stripping three from each end leaves the
         ;; italic behind, which is the right answer for a *bold* toggle.
         ((and (>= (length core) (* 2 width))
               (string-prefix-p mark core)
               (string-suffix-p mark core))
          (let ((inner (substring core width (- (length core) width))))
            (unless (string-match-p (regexp-quote mark) inner)
              (list :text (concat lead inner trail)
                    :cut-before 0 :cut-after 0
                    :sel-start (length lead)
                    :sel-end (+ (length lead) (length inner))))))
         ;; The region sits inside a bold span -- double-click a word in
         ;; `'''release notes''' and you get this, not the case above.
         ((and (string-suffix-p mark head)
               (string-prefix-p mark tail)
               (not (string-match-p (regexp-quote mark) core)))
          (list :text sel :cut-before width :cut-after width
                :sel-start 0 :sel-end len))
         ;; An odd number of markers earlier on the line means the region is
         ;; inside a span that opened before it.  Wrapping would nest, and
         ;; nesting renders as quotes; un-bolding part of a span means
         ;; splitting it, which is a guess about where it should end.
         ((cl-oddp (sumo-wiki--count-bold-marks head)) nil)
         ;; A stray marker inside the region has no single right reading.
         ((string-match-p (regexp-quote mark) core) nil)
         (t
          (list :text (concat lead mark core mark trail)
                :cut-before 0 :cut-after 0
                ;; With nothing marked, point lands between the two runs.
                :sel-start (+ (length lead) width)
                :sel-end (+ (length lead) width (length core)))))))))

;;;###autoload
(defun sumo-wiki-toggle-bold ()
  "Make the region bold, or take the bold off it.

With no region, insert an empty pair of markers and leave point between
them.  The counterpart of `SUMO: Toggle Bold' in VS Code and
`<LocalLeader>b' in the Vim plugin.

Refuses, with a message, on a region spanning lines or one carrying a
stray `''' -- see `sumo-wiki--toggle-bold'."
  (interactive "*")
  (let* ((region (use-region-p))
         (beg (if region (region-beginning) (point)))
         (end (if region (region-end) (point)))
         (edit (and (= (line-number-at-pos beg) (line-number-at-pos end))
                    (sumo-wiki--toggle-bold
                     (buffer-substring-no-properties
                      (save-excursion (goto-char beg) (line-beginning-position))
                      beg)
                     (buffer-substring-no-properties beg end)
                     (buffer-substring-no-properties
                      end
                      (save-excursion (goto-char end) (line-end-position)))))))
    (unless edit
      (user-error
       "Cannot toggle bold here: mark text on one line, clear of any `'''"))
    (let ((from (- beg (plist-get edit :cut-before)))
          (to (+ end (plist-get edit :cut-after))))
      (delete-region from to)
      (goto-char from)
      (insert (plist-get edit :text))
      (if region
          (progn
            (set-mark (+ from (plist-get edit :sel-start)))
            (goto-char (+ from (plist-get edit :sel-end)))
            (activate-mark))
        (goto-char (+ from (plist-get edit :sel-start)))))))

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
    (define-key map (kbd "C-c C-b") #'sumo-wiki-toggle-bold)
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
  ;; Keywords only: the syntax table's comment syntax must not color text.
  (setq-local font-lock-defaults '(sumo-wiki-font-lock-keywords t nil nil nil))
  ;; An edit can change the state of every later line, for example by
  ;; opening `<!--', so refontify the rest of the buffer after it.
  (setq-local jit-lock-contextually t)
  (setq sumo-wiki--state-valid (point-min))
  (add-hook 'after-change-functions #'sumo-wiki--after-change nil t)
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
