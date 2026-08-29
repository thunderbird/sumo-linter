" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.
"
" <Plug> mappings only — defined once, globally, so they can be remapped from a
" vimrc. The ftplugin binds <LocalLeader>l to them buffer-locally.

if exists('g:loaded_sumo_wiki')
  finish
endif
let g:loaded_sumo_wiki = 1

" No <silent>: sumo_wiki#insert_link prompts with input(), and <silent> would
" suppress the prompt itself, leaving the user typing into an invisible reply.
nnoremap <Plug>(sumo-wiki-insert-link) :<C-u>call sumo_wiki#insert_link(0)<CR>
xnoremap <Plug>(sumo-wiki-insert-link) :<C-u>call sumo_wiki#insert_link(1)<CR>
