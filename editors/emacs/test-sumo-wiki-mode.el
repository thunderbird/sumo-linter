;;; test-sumo-wiki-mode.el --- Tests for sumo-wiki-mode -*- lexical-binding: t; -*-

;; This Source Code Form is subject to the terms of the Mozilla Public
;; License, v. 2.0. If a copy of the MPL was not distributed with this
;; file, You can obtain one at https://mozilla.org/MPL/2.0/.

;;; Commentary:

;; Run from the repository root, with the release binaries on PATH:
;;
;;   cargo build --release
;;   PATH="$PWD/target/release:$PATH" emacs -Q --batch -l editors/emacs/test-sumo-wiki-mode.el
;;
;; On macOS, emacs may only exist inside the app bundle:
;;   /Applications/Emacs.app/Contents/MacOS/Emacs
;;
;; The font-lock cases exist because a bare face name in a font-lock rule is
;; evaluated as a variable, so `bold' rather than `\='bold' signalled
;; void-variable on any buffer containing bold text — which is nearly every
;; article. The CLI cases exist because an earlier helper used one temp buffer
;; for both input and output and silently returned the empty string.

;;; Code:

(add-to-list 'load-path (expand-file-name "editors/emacs"))
(require 'sumo-wiki-mode)
(defvar sumo-test-total 0)
(defvar sumo-test-failed 0)

(defun ok (label val)
  "Record assertion LABEL as passing when VAL is non-nil, and print it."
  (setq sumo-test-total (1+ sumo-test-total))
  (unless val (setq sumo-test-failed (1+ sumo-test-failed)))
  (princ (format "  %-46s %s\n" label (if val "PASS" "FAIL"))))

;; 1. byte-compiles and loads
(ok "loads" (featurep 'sumo-wiki-mode))

;; 2. mode activates on a .sumo file
(let ((f (make-temp-file "t" nil ".sumo")))
  (with-current-buffer (find-file-noselect f)
    (ok "activates on .sumo" (eq major-mode 'sumo-wiki-mode))
    (ok "comment-start is <!--" (equal comment-start "<!-- "))
    (ok "tabs disabled" (null indent-tabs-mode))
    (ok "keymap has C-c C-f" (keymapp sumo-wiki-mode-map))))

;; 3. every font-lock regexp is valid and actually matches
(let ((cases '(("= Heading =" . "spaced heading")
               ("=Heading=" . "tight heading")
               ("{for win,mac}x{/for}" . "for block")
               ("{note}x{/note}" . "note")
               ("{key Ctrl+T}" . "key macro")
               ("[[Image:a.png|width=300]]" . "image link")
               ("[[T:Some Template]]" . "template")
               ("[https://x.example lbl]" . "external link")
               ("'''bold'''" . "bold")
               ("__TOC__" . "toc")
               (" indented preformatted" . "preformatted line"))))
  (dolist (c cases)
    (with-temp-buffer
      (sumo-wiki-mode)
      (insert (car c))
      (font-lock-ensure)
      ;; something in the line must have received a face
      (let ((faced nil))
        (goto-char (point-min))
        (while (and (not faced) (not (eobp)))
          (when (get-text-property (point) 'face) (setq faced t))
          (forward-char 1))
        (ok (format "font-lock: %s" (cdr c)) faced)))))

;; 4. eglot registration happens once eglot loads
(require 'eglot)
(ok "eglot server registered" (assq 'sumo-wiki-mode eglot-server-programs))

;; 5. the CLI commands actually work against the real binary
(with-temp-buffer
  (sumo-wiki-mode)
  (insert "see [label](http://e.com) and **b**\n")
  (sumo-wiki-fix-buffer)
  (ok "sumo-wiki-fix-buffer rewrites markdown"
      (and (string-match-p "\\[http://e.com label\\]" (buffer-string))
           (string-match-p "'''b'''" (buffer-string)))))

(with-temp-buffer
  (sumo-wiki-mode)
  (insert "=One=\n=Two=\n= Three =\n")
  (sumo-wiki-apply-style)
  (ok "sumo-wiki-apply-style normalises headings"
      (equal (buffer-string) "=One=\n=Two=\n=Three=\n")))

;; 6. flymake backend parses the CLI's JSON into diagnostics
(with-temp-buffer
  (sumo-wiki-mode)
  (insert "{for win}unclosed\n")
  (let ((got nil))
    (sumo-wiki-flymake-backend (lambda (d &rest _) (setq got d)))
    (ok "flymake backend yields diagnostics"
        (and (listp got) (= 1 (length got))
             (string-match-p "SW001" (flymake-diagnostic-text (car got)))))))

;; 7. yanking a URL over an active region writes a link
;;
;; The pure half first: nil means "just yank", and getting that wrong destroys
;; whatever was on the clipboard, so the negative cases matter most.
(ok "URL over prose becomes a link"
    (equal (sumo-wiki--link-from-paste "https://example.org" "the release notes")
           "[https://example.org the release notes]"))
(ok "whitespace around both is trimmed"
    (equal (sumo-wiki--link-from-paste "  https://example.org\n" " release notes ")
           "[https://example.org release notes]"))
(ok "mailto counts as a URL"
    (equal (sumo-wiki--link-from-paste "mailto:a@b.org" "write to us")
           "[mailto:a@b.org write to us]"))
(ok "no region yanks normally"
    (null (sumo-wiki--link-from-paste "https://example.org" "")))
(ok "non-URL kill yanks normally"
    (null (sumo-wiki--link-from-paste "some words" "the release notes")))
(ok "prose starting with a scheme yanks normally"
    (null (sumo-wiki--link-from-paste "https://example.org and more" "x")))
(ok "URL over a URL yanks normally"
    (null (sumo-wiki--link-from-paste "https://b.org" "https://a.org")))
(ok "multi-line region yanks normally"
    (null (sumo-wiki--link-from-paste "https://example.org" "one\ntwo")))
(ok "region with brackets yanks normally"
    (null (sumo-wiki--link-from-paste "https://example.org" "[[Config Editor]]")))
(ok "never produces markdown"
    (null (string-match-p "\\](" (sumo-wiki--link-from-paste
                                 "https://example.org" "here"))))

;; Then the command, in a real buffer with a real kill ring.
;;
;; `transient-mark-mode' is nil under --batch but t in any interactive Emacs,
;; and `use-region-p' consults it -- deliberately, so that anyone who turns the
;; mode off keeps a plain `C-y'. Bind it here or the region is invisible to the
;; command and these cases pass vacuously.
(let ((transient-mark-mode t))
  (with-temp-buffer
    (sumo-wiki-mode)
    (insert "See the release notes for details.\n")
    (goto-char (point-min))
    (search-forward "the release notes")
    (push-mark (match-beginning 0) t t)
    (kill-new "https://example.org")
    (sumo-wiki-yank)
    (ok "sumo-wiki-yank writes the link"
        (equal (buffer-string)
               "See [https://example.org the release notes] for details.\n"))))

;; A non-URL kill over a region is an ordinary yank, region and all.
(let ((transient-mark-mode t))
  (with-temp-buffer
    (sumo-wiki-mode)
    (insert "See the release notes.\n")
    (goto-char (point-min))
    (search-forward "the release notes")
    (push-mark (match-beginning 0) t t)
    (kill-new "some words")
    (sumo-wiki-yank)
    (ok "a non-URL kill over a region just yanks"
        (equal (buffer-string) "See the release notessome words.\n"))))

(with-temp-buffer
  (sumo-wiki-mode)
  (insert "See  for details.\n")
  (goto-char (point-min))
  (search-forward "See ")
  (kill-new "https://example.org")
  (sumo-wiki-yank)
  (ok "sumo-wiki-yank with no region is a plain yank"
      (equal (buffer-string) "See https://example.org for details.\n")))

(let ((transient-mark-mode t))
  (with-temp-buffer
    (sumo-wiki-mode)
    (insert "See the release notes.\n")
    (goto-char (point-min))
    (search-forward "the release notes")
    (push-mark (match-beginning 0) t t)
    (kill-new "https://example.org")
    (let ((sumo-wiki-paste-url-as-link nil))
      (sumo-wiki-yank))
    (ok "the opt-out restores plain yanking"
        (equal (buffer-string) "See the release noteshttps://example.org.\n"))))

;; `yank' is remapped rather than bound to a key, so this follows whatever the
;; user has yank on -- C-y, and s-v on macOS.
(with-temp-buffer
  (sumo-wiki-mode)
  (ok "yank is remapped in the mode map"
      (eq (lookup-key sumo-wiki-mode-map [remap yank]) 'sumo-wiki-yank))
  (ok "C-y resolves to it" (eq (key-binding (kbd "C-y")) 'sumo-wiki-yank)))

;; delete-selection-mode deletes the region in pre-command-hook, which would
;; leave the command with no link text. The property has to say "not this time".
(let ((transient-mark-mode t))
  (with-temp-buffer
    (sumo-wiki-mode)
    (insert "the release notes")
    (push-mark (point-min) t t)
    (goto-char (point-max))
    (kill-new "https://example.org")
    (ok "delsel is suppressed for a link yank"
        (null (sumo-wiki--yank-delete-selection)))
    (kill-new "just some text")
    (ok "delsel behaves normally otherwise"
        (eq (sumo-wiki--yank-delete-selection) 'yank))))

;;; Summary and exit status
;;
;; `--batch' exits 0 however many FAILs were printed, so without this the whole
;; file is decoration: CI would go green on a broken mode. An error signalled
;; anywhere above aborts the run with a backtrace and a non-zero status already;
;; this handles the case where an assertion merely returns nil.
;;
;; The count is also a floor, because a `let' form that stops running its body
;; would otherwise just print fewer lines and still pass. Raise it when adding
;; assertions.

(let ((expected 38))
  (when (< sumo-test-total expected)
    (setq sumo-test-failed (1+ sumo-test-failed))
    (princ (format "  %-46s FAIL (ran %d)\n"
                   (format "at least %d assertions ran" expected)
                   sumo-test-total))))

(princ (format "emacs: %d/%d assertions passed\n"
               (- sumo-test-total sumo-test-failed) sumo-test-total))
(kill-emacs (if (> sumo-test-failed 0) 1 0))

;;; test-sumo-wiki-mode.el ends here
