" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.
"
" Paste-a-URL-over-a-selection for SUMO wiki markup, the same gesture VS Code,
" Markdown mode and the Emacs mode use. Linting still comes from
" sumo-lint-lsp; this file is only the editing helper, so there is no overlap.
"
" SUMO has two link forms and they are not interchangeable:
"   [https://example.org label]   external, scheme required, space-separated
"   [[Article title|label]]       internal, by *title* (not slug), pipe-separated
" Only the external form can be built from a clipboard URL: an internal link
" goes by article title, which a /kb/<slug> URL does not carry.

function! sumo_wiki#is_url(text) abort
  return a:text =~? '^\%(https\?\|ftp\|mailto\):'
endfunction

" The pure half, so the tests need no buffer and no visual mode.
" An empty string means "paste normally", and every case that is not
" unambiguously select-then-paste-a-URL returns it: a paste mapping that
" guesses is worse than no paste mapping, because what it silently mangles is
" whatever was in the register.
function! sumo_wiki#link_from_paste(pasted, selected) abort
  let l:url = trim(a:pasted)
  let l:text = trim(a:selected)
  " A URL never contains whitespace, so anything that does is prose that merely
  " starts with a scheme, and pasting it over a selection is a plain replace.
  if !sumo_wiki#is_url(l:url) || l:url =~# '\_s'
    return ''
  endif
  " Nothing selected means no link text; replacing one URL with another is a
  " correction, not a link.
  if empty(l:text) || sumo_wiki#is_url(l:text)
    return ''
  endif
  " A multi-line selection has no sensible label, and brackets would close the
  " link early. `|` is safe here: it only separates in the [[internal]] form.
  if stridx(l:text, "\n") >= 0 || l:text =~# '[][]'
    return ''
  endif
  return '[' . l:url . ' ' . l:text . ']'
endfunction

function! s:enabled() abort
  return get(b:, 'sumo_wiki_paste_url_as_link',
        \ get(g:, 'sumo_wiki_paste_url_as_link', 1))
endfunction

" KEYS is 'p' or 'P' — whichever the user actually pressed, so the fallback is
" the paste they asked for rather than an approximation of it.
function! sumo_wiki#visual_paste(keys) abort
  let l:reg = v:register
  " Rebuild exactly what was typed, count included, so the fallback is the
  " user's paste rather than an approximation of it.
  let l:fallback = 'normal! gv"' . l:reg
        \ . (v:count > 0 ? v:count : '') . a:keys

  " Bail out to the ordinary paste on anything ambiguous. A count means "paste
  " it N times", which one link is not; a linewise or blockwise register is a
  " chunk of text the user meant to place, not a URL they copied; and a
  " multi-line or non-charwise selection has no single label.
  if !s:enabled() || v:count > 0
        \ || visualmode() !=# 'v' || getregtype(l:reg) !=# 'v'
    execute l:fallback
    return
  endif

  let [l:lnum, l:startcol] = getpos("'<")[1:2]
  let [l:endlnum, l:endcol] = getpos("'>")[1:2]
  if l:lnum != l:endlnum
    execute l:fallback
    return
  endif

  " With 'selection' inclusive, '> holds the first byte of the last selected
  " character, so step past the whole character — a multibyte label would
  " otherwise be cut mid-codepoint.
  let l:line = getline(l:lnum)
  if &selection ==# 'exclusive'
    let l:after = l:endcol
  else
    let l:after = l:endcol + strlen(matchstr(l:line, '.', l:endcol - 1))
  endif
  let l:selected = strpart(l:line, l:startcol - 1, l:after - l:startcol)

  let l:link = sumo_wiki#link_from_paste(getreg(l:reg), l:selected)
  if empty(l:link)
    execute l:fallback
    return
  endif

  " setline rather than a register round-trip: yanking the selection to read it
  " would write to the system clipboard under 'clipboard=unnamed' and destroy
  " the very URL being pasted.
  call setline(l:lnum, strpart(l:line, 0, l:startcol - 1) . l:link
        \ . strpart(l:line, l:after - 1))
  call cursor(l:lnum, l:startcol + strlen(l:link) - 1)
endfunction
