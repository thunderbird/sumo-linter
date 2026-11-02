" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.

autocmd BufRead,BufNewFile *.sumo setfiletype sumo-wiki

" `.wiki` is claimed by other wiki plugins too, such as vimwiki, so a file type
" that one of them set stays. But Vim and Neovim themselves call every `*.wiki`
" file `mediawiki`, so yielding to that guess meant a `.wiki` file never got
" this plugin (#38). sumo_wiki#claim_wiki() overrides only the guess, and
" `let g:sumo_wiki_claim_wiki = 0` turns it off.
autocmd BufRead,BufNewFile *.wiki call sumo_wiki#claim_wiki()
