" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.
"
" Run from the repository root, under Vim or Neovim:
"
"   vim  -es -Nu NONE -S editors/vim/test/test-sumo-wiki.vim
"   nvim -es -u NONE  -S editors/vim/test/test-sumo-wiki.vim
"
" The end-to-end cases drive the real `p` mapping through :normal, because the
" pure function passing tells you nothing about whether the mapping is wired
" up, which columns it reads, or whether it clobbers the register.

set nocompatible
let s:root = fnamemodify(resolve(expand('<sfile>:p')), ':h:h')
execute 'set runtimepath^=' . fnameescape(s:root)
filetype plugin on

let s:total = 0
let s:failed = 0

" `:echo` writes nothing under -es, so results go straight to stdout.
function! s:say(msg) abort
  call writefile([a:msg], '/dev/stdout', 'a')
endfunction

function! s:ok(label, got, want) abort
  let s:total += 1
  if a:got ==# a:want
    call s:say(printf('  %-46s PASS', a:label))
  else
    let s:failed += 1
    call s:say(printf('  %-46s FAIL', a:label))
    call s:say(printf('      want %s', string(a:want)))
    call s:say(printf('      got  %s', string(a:got)))
  endif
endfunction

" --- link_from_paste --------------------------------------------------------
" '' means "paste normally". The negative cases matter more than the positive
" one: getting them wrong destroys what was in the register.
call s:ok('URL over prose becomes a link',
      \ sumo_wiki#link_from_paste('https://example.org', 'the release notes'),
      \ '[https://example.org the release notes]')
call s:ok('surrounding whitespace is trimmed',
      \ sumo_wiki#link_from_paste("  https://example.org\n", '  release notes  '),
      \ '[https://example.org release notes]')
call s:ok('a query string survives',
      \ sumo_wiki#link_from_paste('https://e.org/a?b=1&c=2', 'here'),
      \ '[https://e.org/a?b=1&c=2 here]')
call s:ok('mailto counts as a URL',
      \ sumo_wiki#link_from_paste('mailto:a@b.org', 'write to us'),
      \ '[mailto:a@b.org write to us]')
call s:ok('a pipe in the label is fine externally',
      \ sumo_wiki#link_from_paste('https://example.org', 'a|b'),
      \ '[https://example.org a|b]')

call s:ok('empty selection pastes normally',
      \ sumo_wiki#link_from_paste('https://example.org', ''), '')
call s:ok('non-URL register pastes normally',
      \ sumo_wiki#link_from_paste('some words', 'the release notes'), '')
call s:ok('empty register pastes normally',
      \ sumo_wiki#link_from_paste('', 'the release notes'), '')
call s:ok('prose starting with a scheme pastes normally',
      \ sumo_wiki#link_from_paste('https://example.org and more', 'x'), '')
call s:ok('multi-line register pastes normally',
      \ sumo_wiki#link_from_paste("https://a.org\nhttps://b.org", 'x'), '')
call s:ok('URL over a URL pastes normally',
      \ sumo_wiki#link_from_paste('https://b.org', 'https://a.org'), '')
call s:ok('multi-line selection pastes normally',
      \ sumo_wiki#link_from_paste('https://example.org', "one\ntwo"), '')
call s:ok('selection with brackets pastes normally',
      \ sumo_wiki#link_from_paste('https://example.org', '[[Config Editor]]'), '')
call s:ok('paste never produces markdown',
      \ sumo_wiki#link_from_paste('https://example.org', 'here') =~# '](', 0)

call s:ok('isUrl https', sumo_wiki#is_url('https://example.org'), 1)
call s:ok('isUrl is case-insensitive', sumo_wiki#is_url('HTTPS://example.org'), 1)
call s:ok('isUrl needs a scheme', sumo_wiki#is_url('example.org'), 0)
call s:ok('a title is not a URL', sumo_wiki#is_url('Install Thunderbird'), 0)

" --- the mapping, end to end ------------------------------------------------
" Selects "the release notes" in "See the release notes for details." — 0w puts
" the cursor on `the` and 3e reaches the final `s` of `notes`.
" Returns the whole buffer: a linewise register splits the line into three, and
" checking only line 1 would call that a pass.
function! s:paste_over(text, register, regtype, keys) abort
  enew!
  setfiletype sumo-wiki
  call setline(1, a:text)
  call setreg('"', a:register, a:regtype)
  execute 'normal 0wv3e' . a:keys
  return join(getline(1, '$'), "\n")
endfunction

enew!
setfiletype sumo-wiki
call s:ok('ftplugin maps p in visual mode', maparg('p', 'x') !=# '', 1)
call s:ok('ftplugin maps P in visual mode', maparg('P', 'x') !=# '', 1)

call s:ok('p over a selection writes the link',
      \ s:paste_over('See the release notes for details.',
      \              'https://example.org', 'v', 'p'),
      \ 'See [https://example.org the release notes] for details.')
call s:ok('P over a selection writes the link too',
      \ s:paste_over('See the release notes for details.',
      \              'https://example.org', 'v', 'P'),
      \ 'See [https://example.org the release notes] for details.')
call s:ok('a non-URL register pastes as usual',
      \ s:paste_over('See the release notes for details.',
      \              'some words', 'v', 'p'),
      \ 'See some words for details.')
" A linewise register is a chunk of text the user meant to place, not a URL
" they copied, so it must reach the ordinary paste path.
call s:ok('a linewise register pastes as usual',
      \ s:paste_over('See the release notes for details.',
      \              'https://example.org', 'V', 'p'),
      \ "See \nhttps://example.org\n for details.")

" A count means "paste it N times", which one link is not — and the fallback
" has to carry the count through, or 2p silently pastes once.
call s:ok('a count falls through to a plain paste',
      \ s:paste_over('See the release notes for details.',
      \              'https://example.org', 'v', '2p'),
      \ 'See https://example.orghttps://example.org for details.')

" The register must survive: `p` over a selection normally swaps the selection
" into the unnamed register, and the link path must not do that either way.
enew!
setfiletype sumo-wiki
call setline(1, 'See the release notes for details.')
call setreg('"', 'https://example.org', 'v')
normal 0wv3ep
call s:ok('the register still holds the URL', getreg('"'), 'https://example.org')

" Multibyte: '> holds the first byte of the last character, so a naive slice
" cuts it in half and produces mojibake.
enew!
setfiletype sumo-wiki
call setline(1, 'See le café for details.')
call setreg('"', 'https://example.org', 'v')
normal 0wv2ep
call s:ok('a multibyte label is not cut in half', getline(1),
      \ 'See [https://example.org le café] for details.')

" 'selection' exclusive puts '> one byte past the selection instead of on the
" last character's first byte. Vim compensates the `e` motion, so the same keys
" select the same words — and the column arithmetic has to agree.
set selection=exclusive
call s:ok('selection=exclusive selects the same span',
      \ s:paste_over('See the release notes for details.',
      \              'https://example.org', 'v', 'p'),
      \ 'See [https://example.org the release notes] for details.')
set selection=inclusive

" ftdetect: the plugin directory should be enough on its own, with no
" `au BufRead` line in the user's vimrc.
let s:tmp = tempname() . '.sumo'
call writefile(['= Heading ='], s:tmp)
" Start from a buffer that is neither, or both assertions pass vacuously on
" whatever the previous case left behind. `edit!` because the paste cases above
" leave a modified [No Name] buffer, and plain `edit` would abort with E37.
enew!
setlocal filetype= noexpandtab
execute 'edit! ' . fnameescape(s:tmp)
call s:ok('.sumo is detected as sumo-wiki', &filetype, 'sumo-wiki')
call s:ok('expandtab is set by the ftplugin', &expandtab, 1)
bwipeout!
call delete(s:tmp)

" The opt-out has to reach the plain paste, not a no-op.
enew!
setfiletype sumo-wiki
let g:sumo_wiki_paste_url_as_link = 0
call setline(1, 'See the release notes for details.')
call setreg('"', 'https://example.org', 'v')
normal 0wv3ep
call s:ok('the opt-out restores plain pasting', getline(1),
      \ 'See https://example.org for details.')
unlet g:sumo_wiki_paste_url_as_link

" A floor on the count: a file that stops running its body would otherwise
" print no failures and pass.
let s:expected = 31
if s:total < s:expected
  let s:failed += 1
  call s:say(printf('  only %d assertions ran, expected at least %d', s:total, s:expected))
endif

call s:say(printf('vim: %d/%d assertions passed', s:total - s:failed, s:total))
if s:failed > 0
  cquit!
endif
qall!
