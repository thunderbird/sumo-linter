" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.

if exists('b:did_ftplugin_sumo_wiki')
  finish
endif
let b:did_ftplugin_sumo_wiki = 1

" Tabs are flagged by the linter, so do not insert them.
setlocal expandtab
setlocal commentstring=<!--\ %s\ -->

let b:undo_ftplugin = 'setlocal expandtab< commentstring<'

if get(g:, 'sumo_wiki_no_mappings', 0)
  finish
endif

" Select some words, then p — a URL in the register becomes a link, anything
" else pastes as usual. `P` too, since it is the same gesture with a different
" register rule.
xnoremap <silent><buffer> p :<C-u>call sumo_wiki#visual_paste('p')<CR>
xnoremap <silent><buffer> P :<C-u>call sumo_wiki#visual_paste('P')<CR>

let b:undo_ftplugin .= ' | silent! xunmap <buffer> p | silent! xunmap <buffer> P'
