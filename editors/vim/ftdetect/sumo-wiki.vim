" This Source Code Form is subject to the terms of the Mozilla Public
" License, v. 2.0. If a copy of the MPL was not distributed with this
" file, You can obtain one at https://mozilla.org/MPL/2.0/.
"
" setfiletype, not `set filetype`: `.wiki` is claimed by other wiki plugins too,
" so yield to anything already handling it rather than override it.
autocmd BufRead,BufNewFile *.sumo,*.wiki setfiletype sumo-wiki
