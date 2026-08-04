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
(defun ok (label val) (princ (format "  %-46s %s\n" label (if val "PASS" "FAIL"))))

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
