(function () {
    var badge = document.getElementById("notification-badge");
    if (!badge) return;

    var countUrl = badge.dataset.countUrl;
    var POLL_INTERVAL_MS = 10000;

    function poll() {
        fetch(countUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                badge.textContent = data.count;
                badge.classList.toggle("hidden", data.count === 0);
            })
            .catch(function () {});
    }

    setInterval(poll, POLL_INTERVAL_MS);
})();
