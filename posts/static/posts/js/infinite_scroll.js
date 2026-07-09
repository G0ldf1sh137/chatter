(function () {
    document.querySelectorAll("[data-infinite-scroll-sentinel]").forEach(function (sentinel) {
        var loading = false;

        function loadMore() {
            var nextUrl = sentinel.dataset.nextUrl;
            if (!nextUrl || loading) return;
            loading = true;
            sentinel.textContent = "Loading…";

            fetch(nextUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    sentinel.insertAdjacentHTML("beforebegin", data.html);
                    sentinel.textContent = "";
                    if (data.next_url) {
                        sentinel.dataset.nextUrl = data.next_url;
                        loading = false;
                    } else {
                        observer.unobserve(sentinel);
                        sentinel.remove();
                    }
                })
                .catch(function () {
                    sentinel.textContent = "";
                    loading = false;
                });
        }

        var observer = new IntersectionObserver(
            function (entries) {
                if (entries[0].isIntersecting) loadMore();
            },
            { rootMargin: "300px" }
        );
        observer.observe(sentinel);
    });
})();
