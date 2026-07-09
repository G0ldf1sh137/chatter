(function () {
    var el = document.getElementById("match-poll");
    if (!el) return;

    var statusUrl = el.dataset.statusUrl;
    var lastUpdated = el.dataset.updatedAt;
    var POLL_INTERVAL_MS = 3000;

    function poll() {
        fetch(statusUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.updated_at !== lastUpdated) {
                    window.location.reload();
                }
            })
            .catch(function () {});
    }

    setInterval(poll, POLL_INTERVAL_MS);
})();
