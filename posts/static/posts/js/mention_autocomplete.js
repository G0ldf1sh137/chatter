(function () {
    var SEARCH_URL = "/users/search/";
    var DEBOUNCE_MS = 200;
    var MAX_SUGGESTIONS = 8;

    var dropdown = null;
    var activeTextarea = null;
    var debounceTimer = null;

    function closeDropdown() {
        if (dropdown) {
            dropdown.remove();
            dropdown = null;
        }
        activeTextarea = null;
    }

    // Matches an "@" immediately before the cursor, preceded by start-of-text
    // or whitespace, followed by zero or more word characters - the typical
    // shape of a mention still being typed.
    function findMentionQuery(textarea) {
        var cursor = textarea.selectionStart;
        var textBeforeCursor = textarea.value.slice(0, cursor);
        var match = textBeforeCursor.match(/(?:^|\s)@(\w*)$/);
        if (!match) return null;
        return { query: match[1], start: cursor - match[1].length - 1 };
    }

    function insertMention(textarea, username, mentionStart) {
        var cursor = textarea.selectionStart;
        var value = textarea.value;
        var inserted = "@" + username + " ";
        textarea.value = value.slice(0, mentionStart) + inserted + value.slice(cursor);
        var newCursor = mentionStart + inserted.length;
        textarea.focus();
        textarea.setSelectionRange(newCursor, newCursor);
        closeDropdown();
    }

    function renderDropdown(textarea, usernames, mentionStart) {
        closeDropdown();
        if (usernames.length === 0) return;

        dropdown = document.createElement("div");
        dropdown.className =
            "absolute z-20 mt-1 max-h-48 w-56 overflow-y-auto rounded-xl border border-border bg-surface py-1 shadow-md";

        usernames.forEach(function (username) {
            var item = document.createElement("button");
            item.type = "button";
            item.textContent = "@" + username;
            item.className = "block w-full px-3 py-1.5 text-left text-sm text-fg hover:bg-surface-hover";
            // mousedown (not click) fires before the textarea would blur, so
            // preventDefault here keeps focus in the textarea for insertMention.
            item.addEventListener("mousedown", function (event) {
                event.preventDefault();
                insertMention(textarea, username, mentionStart);
            });
            dropdown.appendChild(item);
        });

        var rect = textarea.getBoundingClientRect();
        dropdown.style.left = rect.left + window.scrollX + "px";
        dropdown.style.top = rect.bottom + window.scrollY + "px";
        document.body.appendChild(dropdown);
        activeTextarea = textarea;
    }

    document.addEventListener("input", function (event) {
        var textarea = event.target;
        if (!textarea.matches || !textarea.matches('textarea[name="body"]')) return;

        var mention = findMentionQuery(textarea);
        if (!mention) {
            closeDropdown();
            return;
        }

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
            fetch(SEARCH_URL + "?q=" + encodeURIComponent(mention.query))
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    renderDropdown(textarea, data.usernames.slice(0, MAX_SUGGESTIONS), mention.start);
                });
        }, DEBOUNCE_MS);
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeDropdown();
    });

    document.addEventListener("click", function (event) {
        if (dropdown && event.target !== activeTextarea && !dropdown.contains(event.target)) {
            closeDropdown();
        }
    });
})();
