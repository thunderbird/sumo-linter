" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.
"
" Highlighting for SUMO Knowledge Base wiki markup, with the rules and colors
" of SUMO's own editor (sumo-linter #36).
"
" SUMO does not highlight with its wiki parser. Its editor is CodeMirror 5
" with a "simple mode": for each state, regular expressions that are tried in
" order at the current position. The first that matches gives the colors and
" perhaps a new state; if none matches, CodeMirror moves one character on.
" Vim's syntax engine works the same way, except that among the items that
" match at one position the one defined LAST wins. So the rules below are in
" the REVERSE of Kitsune's order. CodeMirror's states are regions here.
"
" The rules are those of Kitsune's kitsune/sumo/static/sumo/js/
" codemirror.sumo-mode.js at commit 908a9601bb628d69aed824bfed68928f2f8983ac,
" translated to Vim patterns, under this license:
"
"   Copyright (c) 2011, 2012, 2013 Mozilla Foundation
"   All rights reserved.
"
"   Redistribution and use in source and binary forms, with or without
"   modification, are permitted provided that the following conditions are
"   met:
"
"   * Redistributions of source code must retain the above copyright notice,
"     this list of conditions and the following disclaimer.
"   * Redistributions in binary form must reproduce the above copyright
"     notice, this list of conditions and the following disclaimer in the
"     documentation and/or other materials provided with the distribution.
"   * Neither the name of the copyright holder nor the names of its
"     contributors may be used to endorse or promote products derived from
"     this software without specific prior written permission.
"
"   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
"   IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
"   THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
"   PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
"   CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
"   EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
"   PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
"   PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
"   LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
"   NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
"   SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"
" editors/highlight-check.mjs compares the result with web/highlight.js over
" every committed article.

if exists('b:current_syntax')
  finish
endif

let s:cpo_save = &cpo
set cpo&vim

syntax case match
" The state at a line depends on everything before it, for example an open
" <!--, as in CodeMirror.
syntax sync fromstart

" JavaScript's \s, less the newline. Vim's own \s is only space and tab.
let s:ws = '[\t\x0b\x0c\r    -     　﻿]'
let s:nonws = '[^\t\x0b\x0c\r    -     　﻿]'
" A {for} condition, as in SUMO's rules.
let s:cond = '\%(\%(,' . s:ws . '\=\)\=\%(not' . s:ws . '\)\='
      \ . '\%(\%(win\%(xp\|7\|8\|10\|11\)\=\|mac\|linux\|android\|maemo\)'
      \ . '\|=\=\%(fx\|tb\|m\|ios\)\d*\)\)\+'

" --- Kitsune's rules, last first ---------------------------------------------

" <!-- starts a comment, up to the first -->, across lines.
syntax region sumoWikiCommentBlock start=/<!--/ end=/-->/

" The rules that apply only at the start of a line.
syntax match sumoWikiTable /^{\=[|!][-+]\=}\=/
syntax match sumoWikiList /^[;:#*]\+/
syntax match sumoWikiRule /^-\{4}/
" The whole line, as on SUMO. The pattern backtracks, so ==H=== is one too.
syntax match sumoWikiHeading /^\(=\{1,6}\)\(.\{-}\)\1$/
execute 'syntax match sumoWikiQuote /^' . s:ws . '\+.*/'

" <nowiki>, <code> and <pre> content, across lines.
syntax region sumoWikiPre matchgroup=sumoWikiSyntax start=/<pre>/ end=/<\/pre>/
syntax region sumoWikiCode matchgroup=sumoWikiSyntax start=/<code>/ end=/<\/code>/
syntax region sumoWikiNowiki matchgroup=sumoWikiSyntax start=/<nowiki>/ end=/<\/nowiki>/

syntax region sumoWikiDel matchgroup=sumoWikiSyntax start=/<del>/ end=/<\/del>/ oneline
syntax region sumoWikiStrikeText matchgroup=sumoWikiSyntax start=/<s>/ end=/<\/s>/ oneline
syntax region sumoWikiUnderlineText matchgroup=sumoWikiSyntax start=/<u>/ end=/<\/u>/ oneline
syntax region sumoWikiItalicText matchgroup=sumoWikiSyntax start=/''/ end=/''/ oneline
syntax region sumoWikiBoldText matchgroup=sumoWikiSyntax start=/'''/ end=/'''/ oneline

" Links, brackets included: [url text], [[Title]], [[Prefix:...]], [[Title|text]].
execute 'syntax match sumoWikiExternalLink /\[' . s:nonws . '*.\{-}]/'
syntax match sumoWikiArticleLink /\[\[.\{-}]]/
execute 'syntax match sumoWikiPrefixedLink /\[\[' . s:nonws . '*:.\{-}]]/'
syntax match sumoWikiPipedLink /\[\[[^]]\{-}|.\{-}]]/

" {menu …}, {key …} and the like: the argument is italic.
syntax region sumoWikiMacro matchgroup=sumoWikiSyntax
      \ start=/{\%(filepath\|key\|menu\|button\|pref\)/ end=/}/ oneline

syntax match sumoWikiBreak /<\/\=br>/
syntax match sumoWikiBlockClose /{\/\%(for\|note\|warning\)}/

" CodeMirror's close_tag state: everything up to the next } is plain.
syntax match sumoWikiCloseTag /\_[^}]*}\=/ contained contains=sumoWikiCloseBrace
syntax match sumoWikiCloseBrace /}/ contained

" {note and {warning, then the close_tag state.
syntax match sumoWikiCallout /{\%(note\|warning\)/ nextgroup=sumoWikiCloseTag

" {for: only a condition or {/for} counts until a condition comes, and a }
" before it is plain. Then the condition, then the close_tag state.
execute 'syntax region sumoWikiFor matchgroup=sumoWikiSyntax start=/{for/'
      \ . ' end=/\ze' . s:cond . '/ contains=sumoWikiForClose nextgroup=sumoWikiForCondition'
syntax match sumoWikiForClose /{\/for}/ contained
execute 'syntax match sumoWikiForCondition /' . s:cond . '/ contained nextgroup=sumoWikiCloseTag'

syntax match sumoWikiToc /__TOC__/

" --- What each item looks like ------------------------------------------------

highlight default link sumoWikiCommentBlock sumoWikiComment
highlight default link sumoWikiTable sumoWikiSyntax
highlight default link sumoWikiList sumoWikiSyntax
highlight default link sumoWikiRule sumoWikiSyntax
highlight default link sumoWikiHeading sumoWikiBold
highlight default link sumoWikiPre sumoWikiComment
highlight default link sumoWikiCode sumoWikiComment
highlight default link sumoWikiNowiki sumoWikiComment
highlight default link sumoWikiDel sumoWikiStrike
highlight default link sumoWikiStrikeText sumoWikiStrike
highlight default link sumoWikiUnderlineText sumoWikiUnderline
highlight default link sumoWikiItalicText sumoWikiItalic
highlight default link sumoWikiBoldText sumoWikiBold
highlight default link sumoWikiExternalLink sumoWikiLink
highlight default link sumoWikiArticleLink sumoWikiLink
highlight default link sumoWikiPrefixedLink sumoWikiLink
highlight default link sumoWikiPipedLink sumoWikiLink
highlight default link sumoWikiMacro sumoWikiItalic
highlight default link sumoWikiBreak sumoWikiSyntax
highlight default link sumoWikiBlockClose sumoWikiSyntax
highlight default link sumoWikiCloseBrace sumoWikiSyntax
highlight default link sumoWikiCallout sumoWikiSyntax
highlight default link sumoWikiForClose sumoWikiSyntax
highlight default link sumoWikiForCondition sumoWikiItalic
highlight default link sumoWikiToc sumoWikiSyntax

" The eight color classes, with SUMO's colors from Kitsune's
" config/themes/_light.scss and _dark.scss, and the nearest 256-color values.
" `default`, so a color scheme or a vimrc can replace any of them. SUMO shows
" bold text in a stronger color, not in bold, so it stays that way here.
function! s:colors() abort
  if &background ==# 'dark'
    highlight default sumoWikiSyntax guifg=#E9A1A1 ctermfg=217
    highlight default sumoWikiLink guifg=#8FBEFA ctermfg=111 gui=underline cterm=underline
    highlight default sumoWikiBold guifg=#F9F9FB ctermfg=231
    highlight default sumoWikiComment guifg=#83D5AD ctermfg=115
    highlight default sumoWikiQuote guifg=#F9F9FB guibg=#3A3D43 ctermfg=231 ctermbg=237
  else
    highlight default sumoWikiSyntax guifg=#D98484 ctermfg=174
    highlight default sumoWikiLink guifg=#5757C2 ctermfg=61 gui=underline cterm=underline
    highlight default sumoWikiBold guifg=#000000 ctermfg=16
    highlight default sumoWikiComment guifg=#009900 ctermfg=28
    highlight default sumoWikiQuote guifg=#FFFFFF guibg=#000000 ctermfg=231 ctermbg=16
  endif
  highlight default sumoWikiItalic gui=italic cterm=italic
  highlight default sumoWikiUnderline gui=underline cterm=underline
  highlight default sumoWikiStrike gui=strikethrough cterm=strikethrough
endfunction
call s:colors()

" A color scheme clears every group, these included, so set them again.
" Changing 'background' with no color scheme clears nothing, so the old colors
" go first. A change made in a vimrc belongs in a ColorScheme autocmd, which
" runs after this one.
let s:groups = ['sumoWikiSyntax', 'sumoWikiLink', 'sumoWikiBold', 'sumoWikiComment',
      \ 'sumoWikiQuote', 'sumoWikiItalic', 'sumoWikiUnderline', 'sumoWikiStrike']
function! s:background() abort
  for g in s:groups
    execute 'highlight clear ' . g
  endfor
  call s:colors()
endfunction
augroup sumo_wiki_colors
  autocmd!
  autocmd ColorScheme * call s:colors()
  autocmd OptionSet background call s:background()
augroup END

let b:current_syntax = 'sumo-wiki'

let &cpo = s:cpo_save
unlet s:cpo_save
