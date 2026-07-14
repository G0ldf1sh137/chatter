(function () {
    var DEBOUNCE_MS = 200;
    var MAX_SUGGESTIONS = 8;

    function createAutocomplete(options) {
        var triggerChar = options.triggerChar;
        var searchUrl = options.searchUrl;
        var resultsKey = options.resultsKey;

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

        // Matches the trigger character immediately before the cursor, preceded
        // by start-of-text or whitespace, followed by zero or more word
        // characters - the typical shape of a mention/tag still being typed.
        var triggerRe = new RegExp("(?:^|\\s)" + triggerChar + "(\\w*)$");

        function findQuery(textarea) {
            var cursor = textarea.selectionStart;
            var textBeforeCursor = textarea.value.slice(0, cursor);
            var match = textBeforeCursor.match(triggerRe);
            if (!match) return null;
            return { query: match[1], start: cursor - match[1].length - 1 };
        }

        function insertResult(textarea, value, matchStart) {
            var cursor = textarea.selectionStart;
            var text = textarea.value;
            var inserted = triggerChar + value + " ";
            textarea.value = text.slice(0, matchStart) + inserted + text.slice(cursor);
            var newCursor = matchStart + inserted.length;
            textarea.focus();
            textarea.setSelectionRange(newCursor, newCursor);
            closeDropdown();
        }

        function renderDropdown(textarea, results, matchStart) {
            closeDropdown();
            if (results.length === 0) return;

            dropdown = document.createElement("div");
            dropdown.className =
                "absolute z-20 mt-1 max-h-48 w-56 overflow-y-auto rounded-xl border border-border bg-surface py-1 shadow-md";

            results.forEach(function (value) {
                var item = document.createElement("button");
                item.type = "button";
                item.textContent = triggerChar + value;
                item.className = "block w-full px-3 py-1.5 text-left text-sm text-fg hover:bg-surface-hover";
                // mousedown (not click) fires before the textarea would blur, so
                // preventDefault here keeps focus in the textarea for insertResult.
                item.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    insertResult(textarea, value, matchStart);
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

            var match = findQuery(textarea);
            if (!match) {
                closeDropdown();
                return;
            }

            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                fetch(searchUrl + "?q=" + encodeURIComponent(match.query))
                    .then(function (response) {
                        return response.json();
                    })
                    .then(function (data) {
                        renderDropdown(textarea, data[resultsKey].slice(0, MAX_SUGGESTIONS), match.start);
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
    }

    createAutocomplete({ triggerChar: "@", searchUrl: "/users/search/", resultsKey: "usernames" });
    createAutocomplete({ triggerChar: "#", searchUrl: "/tags/search/", resultsKey: "names" });
})();
