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

" [lnum, startcol, after] for a single-line charwise selection, or [] for
" anything else. `after` is the 1-based byte column just past the selection:
" with 'selection' inclusive, '> holds the *first byte* of the last character,
" so step past the whole character or a multibyte label is cut in half.
function! s:span() abort
  if visualmode() !=# 'v'
    return []
  endif
  let [l:lnum, l:startcol] = getpos("'<")[1:2]
  let [l:endlnum, l:endcol] = getpos("'>")[1:2]
  if l:lnum != l:endlnum
    return []
  endif
  if &selection ==# 'exclusive'
    return [l:lnum, l:startcol, l:endcol]
  endif
  let l:last = matchstr(getline(l:lnum), '.', l:endcol - 1)
  return [l:lnum, l:startcol, l:endcol + strlen(l:last)]
endfunction

" setline rather than a register round-trip or `normal! i`: yanking the
" selection to read it would write to the system clipboard under
" 'clipboard=unnamed' and destroy the very URL being pasted, and `normal! i`
" runs the text past abbreviations and 'indentkeys'.
function! s:replace(lnum, startcol, after, text) abort
  let l:line = getline(a:lnum)
  call setline(a:lnum, strpart(l:line, 0, a:startcol - 1) . a:text
        \ . strpart(l:line, a:after - 1))
  call cursor(a:lnum, a:startcol + strlen(a:text) - 1)
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
  " chunk of text the user meant to place, not a URL they copied.
  if !s:enabled() || v:count > 0 || getregtype(l:reg) !=# 'v'
    execute l:fallback
    return
  endif

  " A multi-line or non-charwise selection has no single sensible label.
  let l:span = s:span()
  if empty(l:span)
    execute l:fallback
    return
  endif
  let [l:lnum, l:startcol, l:after] = l:span
  let l:selected = strpart(getline(l:lnum), l:startcol - 1, l:after - l:startcol)

  let l:link = sumo_wiki#link_from_paste(getreg(l:reg), l:selected)
  if empty(l:link)
    execute l:fallback
    return
  endif

  call s:replace(l:lnum, l:startcol, l:after, l:link)
endfunction

" --- the type-it-in half ----------------------------------------------------
" The counterpart of `SUMO: Insert Link' in VS Code and `sumo-wiki-insert-link'
" in the Emacs mode, and the only way to write an internal [[Title|text]] link:
" an article title cannot be derived from a URL.

function! sumo_wiki#build_link(target, label) abort
  let l:t = trim(a:target)
  let l:l = trim(a:label)
  if sumo_wiki#is_url(l:t)
    " External: separated by a space, never a pipe. An empty label renders the
    " URL itself.
    return empty(l:l) ? '[' . l:t . ']' : '[' . l:t . ' ' . l:l . ']'
  endif
  " Internal, by article *title*: separated by a pipe. A label identical to the
  " title adds nothing but localizer diff noise.
  if empty(l:l) || l:l ==# l:t
    return '[[' . l:t . ']]'
  endif
  return '[[' . l:t . '|' . l:l . ']]'
endfunction

" '' means accepted, matching VS Code's validateInput contract inverted.
function! sumo_wiki#validate_target(target) abort
  let l:t = trim(a:target)
  if empty(l:t)
    return 'Enter a URL, an article title, or a #w_anchor on this page.'
  endif
  if l:t =~# '[][]'
    return 'A link target cannot contain [ or ].'
  endif
  " In [[Title|text]] the pipe is the separator, so one here would split it.
  if stridx(l:t, '|') >= 0
    return 'A link target cannot contain | -- that separates it from the text.'
  endif
  return ''
endfunction

function! sumo_wiki#validate_label(label, target) abort
  let l:l = trim(a:label)
  if l:l =~# '[][]'
    return 'Link text cannot contain [ or ].'
  endif
  " External links have no pipe syntax, so there it is just a character.
  if stridx(l:l, '|') >= 0 && !sumo_wiki#is_url(trim(a:target))
    return 'Link text cannot contain | in an internal link.'
  endif
  return ''
endfunction

" So the common cases -- select a URL, or select the words you want linked --
" need only one thing typed. A selected link seeds nothing: it would seed
" unusable values, and rewriting an existing link is SW009's quick fix.
function! sumo_wiki#seed_from_selection(selection) abort
  let l:s = trim(a:selection)
  if empty(l:s) || l:s =~# '[][|]' || stridx(l:s, "\n") >= 0
    return {'target': '', 'label': ''}
  endif
  return sumo_wiki#is_url(l:s)
        \ ? {'target': l:s, 'label': ''}
        \ : {'target': '', 'label': l:s}
endfunction

" Re-asks until Validate returns ''. No <silent> on the mappings that reach
" here, or the prompt itself would be suppressed.
function! s:ask(prompt, initial, Validate) abort
  let l:complaint = ''
  while 1
    " No inputsave()/inputrestore(): they save *and clear* the typeahead buffer,
    " which is where feedkeys() puts the answers, so the prompt would block
    " forever under test. The mappings that reach here have no trailing keys for
    " the prompt to eat, so there is nothing to protect.
    let l:answer = input((empty(l:complaint) ? '' : l:complaint . '  ')
          \ . a:prompt, a:initial)
    let l:complaint = a:Validate(l:answer)
    if empty(l:complaint)
      return l:answer
    endif
  endwhile
endfunction

" VISUAL is 1 when called from a visual-mode mapping, in which case the
" selection seeds the prompts and is replaced.
function! sumo_wiki#insert_link(visual) abort
  let l:span = a:visual ? s:span() : []
  let l:selected = empty(l:span)
        \ ? ''
        \ : strpart(getline(l:span[0]), l:span[1] - 1, l:span[2] - l:span[1])
  let l:seed = sumo_wiki#seed_from_selection(l:selected)

  " An empty answer here is how you cancel: input() cannot tell Esc from an
  " empty line, so emptiness is allowed past the validator and checked after.
  let l:target = s:ask('SUMO link target (URL, article title, or #w_anchor): ',
        \ l:seed.target,
        \ { v -> empty(trim(v)) ? '' : sumo_wiki#validate_target(v) })
  if empty(trim(l:target))
    return
  endif

  " An empty label is meaningful for both forms, so there is no cancel here.
  let l:label = s:ask(sumo_wiki#is_url(trim(l:target))
        \ ? 'Link text (empty shows the URL itself): '
        \ : 'Link text (empty shows the article title): ',
        \ l:seed.label,
        \ { v -> sumo_wiki#validate_label(v, l:target) })

  let l:link = sumo_wiki#build_link(l:target, l:label)
  if !empty(l:span)
    call s:replace(l:span[0], l:span[1], l:span[2], l:link)
  else
    " Insert before the character under the cursor, like `i`.
    call s:replace(line('.'), col('.'), col('.'), l:link)
  endif
  redraw
endfunction
